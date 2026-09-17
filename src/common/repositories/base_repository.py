"""
Generic repository with the CRUD/list/search methods every module needs.

Subclass it with a concrete Beanie document and add only the queries specific
to that model. Keep repositories thin: no HTTP exceptions, no business rules,
just data access.

Example
-------
    from src.common.repositories.base_repository import BaseRepository
    from src.widgets.models.widget import Widget

    class WidgetRepository(BaseRepository[Widget]):
        model = Widget

        async def list_active(self, org_id: str) -> list[Widget]:
            return await self.list_by_filter({"org_id": org_id, "status": "active"})

    repo = WidgetRepository()
    widget = await repo.create(Widget(name="x", org_id="org1"))
    widget = await repo.get_by_id(str(widget.id))
    widgets, total = await repo.list_paginated({"org_id": "org1"}, page=1, page_size=20)
    await repo.update(str(widget.id), {"name": "y"})
    await repo.delete(str(widget.id))

Filters are plain Mongo query dicts, so ``{"created_at": {"$gte": dt}}`` works.
"""

import re
from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from beanie import PydanticObjectId
from bson import ObjectId

from src.common.models.base import BaseDocument, utcnow

T = TypeVar("T", bound=BaseDocument)


class BaseRepository(Generic[T]):
    #: Concrete Beanie document class. Set in subclass.
    model: type[T]

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def to_object_id(value: str) -> ObjectId | None:
        """Return an ObjectId or ``None`` if the string is not valid."""
        return ObjectId(value) if ObjectId.is_valid(value) else None

    @staticmethod
    def build_search_query(q: str, fields: Sequence[str], org_id: str) -> dict[str, Any]:
        """
        Case-insensitive regex search across ``fields`` scoped to ``org_id``.

            query = repo.build_search_query("acme", ["name", "description"], org_id)
            results, total = await repo.list_paginated(query, page=1, page_size=10)
        """
        regex = {"$regex": re.escape(q), "$options": "i"}
        return {"$and": [{"$or": [{f: regex} for f in fields]}, {"org_id": org_id}]}

    # ------------------------------------------------------------------- create
    async def create(self, document: T) -> T:
        await document.insert()
        return document

    async def create_many(self, documents: list[T]) -> list[T]:
        if not documents:
            return []
        now = utcnow()
        for d in documents:
            d.updated_at = now
        await self.model.insert_many(documents)
        return documents

    # --------------------------------------------------------------------- read
    async def get_by_id(self, doc_id: str) -> T | None:
        oid = self.to_object_id(doc_id)
        if oid is None:
            return None
        return await self.model.get(PydanticObjectId(oid))

    async def get_by_filter(self, filters: dict[str, Any]) -> T | None:
        return await self.model.find_one(filters)

    async def get_many_by_ids(self, ids: list[str], org_id: str | None = None) -> list[T]:
        oids = [PydanticObjectId(i) for i in ids if ObjectId.is_valid(i)]
        if not oids:
            return []
        query: dict[str, Any] = {"_id": {"$in": oids}}
        if org_id is not None:
            query["org_id"] = org_id
        return await self.model.find(query).to_list()

    async def list_by_filter(
        self, filters: dict[str, Any], sort_by: str = "-created_at"
    ) -> list[T]:
        """All matches (no pagination). ``sort_by``: "+field" / "-field"."""
        return await self.model.find(filters).sort(sort_by).to_list()

    async def list_paginated(
        self,
        filters: dict[str, Any],
        page: int = 1,
        page_size: int = 10,
        sort_by: str = "-created_at",
    ) -> tuple[list[T], int]:
        """
        Returns ``(documents, total_count)``. Sorting/paging happen in Mongo, so
        this stays fast on large collections.
        """
        query = self.model.find(filters)
        total = await query.count()
        skip = max(page - 1, 0) * page_size
        docs = await query.sort(sort_by).skip(skip).limit(page_size).to_list()
        return docs, total

    async def count(self, filters: dict[str, Any]) -> int:
        return await self.model.find(filters).count()

    async def exists(self, filters: dict[str, Any]) -> bool:
        return await self.model.find_one(filters) is not None

    async def aggregate(self, pipeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Raw aggregation passthrough for stats/dashboards."""
        return await self.model.aggregate(pipeline).to_list()

    # ------------------------------------------------------------------- update
    async def update(self, doc_id: str, data: dict[str, Any]) -> T | None:
        """``$set`` the given fields and return the refreshed document."""
        oid = self.to_object_id(doc_id)
        if oid is None:
            return None
        data = {**data, "updated_at": utcnow()}
        await self.model.find_one({"_id": oid}).update({"$set": data})
        return await self.get_by_id(doc_id)

    async def update_many(self, filters: dict[str, Any], data: dict[str, Any]) -> int:
        data = {**data, "updated_at": utcnow()}
        result = await self.model.find(filters).update_many({"$set": data})
        return getattr(result, "modified_count", 0)

    # ------------------------------------------------------------------- delete
    async def delete(self, doc_id: str, org_id: str | None = None) -> bool:
        oid = self.to_object_id(doc_id)
        if oid is None:
            return False
        query: dict[str, Any] = {"_id": oid}
        if org_id is not None:
            query["org_id"] = org_id
        result = await self.model.find_one(query).delete()
        return bool(result and result.deleted_count > 0)

    async def delete_many(self, ids: list[str], org_id: str | None = None) -> int:
        oids = [PydanticObjectId(i) for i in ids if ObjectId.is_valid(i)]
        if not oids:
            return 0
        query: dict[str, Any] = {"_id": {"$in": oids}}
        if org_id is not None:
            query["org_id"] = org_id
        result = await self.model.find(query).delete()
        return result.deleted_count if result else 0

    async def delete_by_filter(self, filters: dict[str, Any]) -> int:
        result = await self.model.find(filters).delete()
        return result.deleted_count if result else 0
