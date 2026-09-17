"""
Background tasks for items (Taskiq worker).

Run the worker:
    taskiq worker --workers 2 --max-async-tasks 50 --ack-type when_received \
        src.taskiq_brokers:items_broker src.items.tasks

Pattern for every task:
1. Thin ``@broker.task`` wrapper that only handles job tracking.
2. Private ``_do_work`` coroutine with the real logic (easy to unit test).
3. Instantiate repositories/utils directly (no FastAPI DI in workers).
"""

import logging
import os

from src.common.prompts import SUMMARIZE_DOCUMENT_SYSTEM_PROMPT, SUMMARIZE_DOCUMENT_USER_PROMPT
from src.common.services.file_service import md5_of_file
from src.common.utils.aws_utils import AwsUtil
from src.common.utils.document_utils import DocumentUtil
from src.common.utils.job_tracker import JobTracker
from src.common.utils.llm_util import get_default_llm_util
from src.core.config import DEFAULT_LLM_MODEL
from src.items.enums.item_status import ItemStatus
from src.items.repositories.item_repository import ItemRepository
from src.items.schemas.responses.llm_item_summary import LLMItemSummary
from src.taskiq_brokers import items_broker

logger = logging.getLogger(__name__)


@items_broker.task(task_name="process_item")
async def process_item_task(item_id: str, job_id: str | None = None) -> None:
    """Download the item's file, detect duplicates, summarise with the LLM."""
    repo = ItemRepository()
    try:
        async with JobTracker.run(job_id, item_id):
            await _process_item(item_id, repo)
    except Exception as e:  # noqa: BLE001
        # JobTracker already recorded the failure; persist it on the document too.
        await repo.update(item_id, {"status": ItemStatus.FAILED.value, "error": str(e)})


async def _process_item(item_id: str, repo: ItemRepository) -> None:
    item = await repo.get_by_id(item_id)
    if not item:
        raise ValueError(f"Item {item_id} not found")
    if not item.aws_object_name:
        # Nothing to process for JSON-created items.
        await repo.update(item_id, {"status": ItemStatus.ACTIVE.value})
        return

    await repo.update(item_id, {"status": ItemStatus.PROCESSING.value})

    aws = AwsUtil()
    docs = DocumentUtil()
    temp_path = await aws.download_file_from_s3(item.aws_object_name)
    try:
        # ---- duplicate detection (size window, then hash) --------------------
        file_hash = md5_of_file(temp_path)
        size = item.file_size or os.path.getsize(temp_path)
        candidates = await repo.list_by_file_size_range(
            item.org_id, max(size - 1024, 0), size + 1024
        )
        original = None
        if candidates:
            original = await repo.get_by_hashed_content(item.org_id, file_hash)
            if original and str(original.id) == item_id:
                original = None
        await repo.update(
            item_id,
            {
                "hashed_content": file_hash,
                "is_duplicate": original is not None,
                "duplicate_of": str(original.id) if original else None,
            },
        )

        # ---- text extraction --------------------------------------------------
        text = await docs.extract_text(temp_path, item.file_type or "")
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass

    # ---- LLM structured summary --------------------------------------------
    metadata: dict = {}
    if text.strip():
        llm = get_default_llm_util()
        summary: LLMItemSummary = await llm.get_llm_response(
            prompt=SUMMARIZE_DOCUMENT_USER_PROMPT.format(document_text=text[:100_000]),
            structure=LLMItemSummary,
            system_prompt=SUMMARIZE_DOCUMENT_SYSTEM_PROMPT,
            model=DEFAULT_LLM_MODEL,
            thinking="low",
        )
        metadata = summary.model_dump()
    else:
        logger.warning(f"Item {item_id}: no text extracted, skipping LLM step")

    await repo.update(
        item_id, {"status": ItemStatus.ACTIVE.value, "metadata": metadata, "error": None}
    )
    logger.info(f"Item {item_id} processed")
