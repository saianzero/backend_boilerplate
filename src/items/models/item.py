"""
Example document: ``Item``.

Shows the fields every tenant-scoped model should carry (``org_id``,
``uploaded_by``), an enum status, optional attached file metadata, and a
free-form ``metadata`` dict for LLM/extracted output.

Copy this file, rename the class, adjust fields, and it is picked up by
``Database.connect()`` automatically (it lives under ``models/``).
"""

from pymongo import ASCENDING, DESCENDING, IndexModel

from src.common.models.base import BaseDocument
from src.items.enums.item_status import ItemStatus


class Item(BaseDocument):
    # Core fields
    name: str
    description: str = ""
    status: ItemStatus = ItemStatus.PENDING
    tags: list[str] = []

    # Ownership / tenancy - include on every model
    org_id: str = ""
    uploaded_by: str = ""

    # Optional attached file (set when created via presigned-upload flow)
    file_name: str | None = None
    file_type: str | None = None  # MIME type
    file_size: int | None = None  # bytes
    aws_object_name: str | None = None  # S3 key
    hashed_content: str = ""  # md5 for duplicate detection
    is_duplicate: bool = False
    duplicate_of: str | None = None  # id of the original

    # Output of background processing (LLM summary etc.)
    metadata: dict | None = None
    error: str | None = None

    class Settings:
        name = "items"
        indexes = [
            IndexModel([("org_id", ASCENDING), ("updated_at", DESCENDING)]),
            IndexModel([("org_id", ASCENDING), ("status", ASCENDING)]),
            IndexModel([("org_id", ASCENDING), ("hashed_content", ASCENDING)]),
            "uploaded_by",
        ]
