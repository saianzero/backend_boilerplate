"""
Business logic for items.

Services own: validation, authorisation (org scoping), orchestration of
repositories/utils, dispatching background tasks, and raising
``HTTPException``. Repositories stay dumb; routers stay thin.

Every public method takes the ``CurrentUser`` so tenant scoping is explicit.
"""

import builtins
import logging
import uuid
from typing import Any

from fastapi import HTTPException

from src.common.schemas.internal.current_user import CurrentUser
from src.common.schemas.responses.pagination import PaginatedResponse
from src.common.utils.aws_utils import AwsUtil
from src.common.utils.job_tracker import JobTracker
from src.common.utils.serialize_utils import serialize_document
from src.items.enums.item_status import ItemStatus
from src.items.models.item import Item
from src.items.repositories.item_repository import ItemRepository
from src.items.schemas.requests.create_item import (
    CreateItemRequest,
    PresignRequest,
    UploadedItemRequest,
)
from src.items.schemas.requests.list_items import ListItemsRequest
from src.items.schemas.requests.update_item import UpdateItemRequest

logger = logging.getLogger(__name__)


class ItemService:
    def __init__(self, item_repository: ItemRepository, aws_utils: AwsUtil):
        self.repo = item_repository
        self.aws = aws_utils

    # ------------------------------------------------------------- helpers --
    async def _get_owned(self, item_id: str, user: CurrentUser) -> Item:
        """Fetch or raise 400/404/403. Reuse in every method that touches one item."""
        if self.repo.to_object_id(item_id) is None:
            raise HTTPException(status_code=400, detail="Invalid item id")
        item = await self.repo.get_by_id(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        if item.org_id != user.org_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        return item

    @staticmethod
    def _to_dict(item: Item) -> dict[str, Any]:
        return serialize_document(item)

    # -------------------------------------------------------------- create --
    async def create(self, request: CreateItemRequest, user: CurrentUser) -> dict[str, Any]:
        item = Item(
            name=request.name,
            description=request.description,
            tags=request.tags,
            metadata=request.metadata,
            status=ItemStatus.ACTIVE,
            org_id=user.org_id,
            uploaded_by=str(user.id),
        )
        await self.repo.create(item)
        return self._to_dict(item)

    async def presign_uploads(
        self, files: list[PresignRequest], user: CurrentUser
    ) -> list[dict[str, Any]]:
        """Step 1 of the upload flow: one PUT url per file."""
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")
        out = []
        for f in files:
            key = f"{user.org_id}/items/{uuid.uuid4()}_{f.file_name}"
            out.append(
                {
                    "file_name": f.file_name,
                    "file_type": f.file_type,
                    "file_size": f.file_size,
                    "aws_object_name": key,
                    "upload_url": self.aws.generate_presigned_put_url(key, f.file_type),
                }
            )
        return out

    async def create_from_uploads(
        self, uploads: list[UploadedItemRequest], user: CurrentUser
    ) -> dict[str, Any]:
        """
        Step 2: files are in S3. Create one Item per file and queue a background
        task for each. Progress is tracked under one ``job_id``.
        """
        if not uploads:
            raise HTTPException(status_code=400, detail="No uploads provided")

        # Imported here to avoid importing the broker at module import time.
        from src.items.tasks import process_item_task

        job_id = await JobTracker.create(user.id, user.org_id, total=len(uploads))
        created: list[Item] = []

        for up in uploads:
            fd = up.file_data
            try:
                item = Item(
                    name=up.name or fd.file_name,
                    tags=up.tags,
                    status=ItemStatus.PENDING,
                    file_name=fd.file_name,
                    file_type=fd.file_type,
                    file_size=fd.file_size,
                    aws_object_name=up.aws_object_name,
                    org_id=user.org_id,
                    uploaded_by=str(user.id),
                )
                await self.repo.create(item)
                item_id = str(item.id)
                await JobTracker.mark(job_id, item_id, "queued")
                await process_item_task.kiq(item_id, job_id)
                created.append(item)
            except Exception as e:  # noqa: BLE001
                logger.error(f"Failed to queue item {fd.file_name}: {e}")
                await JobTracker.mark(job_id, f"failed_{fd.file_name}", "failed", error=str(e))

        return {
            "job_id": job_id,
            "total": len(uploads),
            "status": "queued",
            "items": [{"id": str(i.id), "name": i.name} for i in created],
        }

    async def job_status(self, job_id: str, user: CurrentUser) -> dict[str, Any]:
        job = await JobTracker.get(job_id, requesting_user_id=user.id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    # ---------------------------------------------------------------- read --
    async def get(self, item_id: str, user: CurrentUser) -> dict[str, Any]:
        item = await self._get_owned(item_id, user)
        data = self._to_dict(item)
        if item.aws_object_name:
            data["file_url"] = self.aws.get_presigned_url(item.aws_object_name)
        return data

    async def list(self, request: ListItemsRequest, user: CurrentUser) -> PaginatedResponse:
        filters = {**request.get_filters(), "org_id": user.org_id}
        docs, total = await self.repo.list_paginated(
            filters, page=request.page, page_size=request.page_size, sort_by=request.get_sort()
        )
        return PaginatedResponse.build(
            [self._to_dict(d) for d in docs],
            total=total,
            page=request.page,
            page_size=request.page_size,
        )

    async def search(
        self, q: str, user: CurrentUser, page: int = 1, page_size: int = 10
    ) -> dict[str, Any]:
        docs, total = await self.repo.search(q, user.org_id, page, page_size)
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "data": [self._to_dict(d) for d in docs],
        }

    async def stats(self, user: CurrentUser) -> dict[str, Any]:
        return {
            "by_status": await self.repo.count_by_status(user.org_id),
            "added_last_30_days": await self.repo.added_in_last_days(user.org_id, 30),
            "recent": [self._to_dict(d) for d in await self.repo.recent(user.org_id, 5)],
        }

    # -------------------------------------------------------------- update --
    async def update(
        self, item_id: str, request: UpdateItemRequest, user: CurrentUser
    ) -> dict[str, Any]:
        await self._get_owned(item_id, user)
        changes = request.changed_fields()
        if not changes:
            raise HTTPException(status_code=400, detail="No fields to update")
        updated = await self.repo.update(item_id, changes)
        return self._to_dict(updated)

    async def reprocess(self, item_ids: builtins.list[str], user: CurrentUser) -> dict[str, Any]:
        """Re-run the background task for existing items."""
        from src.items.tasks import process_item_task

        items = await self.repo.get_many_by_ids(item_ids, org_id=user.org_id)
        if not items:
            raise HTTPException(status_code=404, detail="No items found")
        job_id = await JobTracker.create(user.id, user.org_id, total=len(items))
        for item in items:
            await self.repo.update(
                str(item.id), {"status": ItemStatus.PROCESSING.value, "error": None}
            )
            await JobTracker.mark(job_id, str(item.id), "queued")
            await process_item_task.kiq(str(item.id), job_id)
        return {"job_id": job_id, "total": len(items), "status": "queued"}

    # -------------------------------------------------------------- delete --
    async def delete(self, item_id: str, user: CurrentUser) -> dict[str, Any]:
        item = await self._get_owned(item_id, user)
        if not item.is_duplicate and await self.repo.has_duplicates(item_id):
            raise HTTPException(
                status_code=409, detail="Delete duplicates before deleting the original"
            )
        if item.aws_object_name:
            self.aws.delete_object(item.aws_object_name)
        await self.repo.delete(item_id, org_id=user.org_id)
        return {"message": "Item deleted", "id": item_id}

    async def bulk_delete(self, item_ids: builtins.list[str], user: CurrentUser) -> dict[str, Any]:
        items = await self.repo.get_many_by_ids(item_ids, org_id=user.org_id)
        deletable, blocked = [], []
        for item in items:
            sid = str(item.id)
            if not item.is_duplicate and await self.repo.has_duplicates(sid):
                blocked.append(sid)
            else:
                deletable.append(item)
        if not deletable:
            raise HTTPException(status_code=400, detail="Nothing deletable in the given ids")
        for item in deletable:
            if item.aws_object_name:
                self.aws.delete_object(item.aws_object_name)
        deleted = await self.repo.delete_many([str(i.id) for i in deletable], org_id=user.org_id)
        return {
            "message": f"Deleted {deleted} item(s).",
            "deleted_count": deleted,
            "not_deleted_ids": blocked,
        }
