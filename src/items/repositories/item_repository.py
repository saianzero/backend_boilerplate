"""
Data access for ``Item``. Inherits CRUD/list/search from ``BaseRepository``
and adds only Item-specific queries.
"""

from datetime import timedelta

from src.common.models.base import utcnow
from src.common.repositories.base_repository import BaseRepository
from src.items.models.item import Item

SEARCH_FIELDS = ("name", "description", "tags")


class ItemRepository(BaseRepository[Item]):
    model = Item

    # ---------------------------------------------------------------- search --
    async def search(
        self, q: str, org_id: str, page: int, page_size: int
    ) -> tuple[list[Item], int]:
        query = self.build_search_query(q, SEARCH_FIELDS, org_id)
        query["$and"].append({"is_duplicate": False})
        return await self.list_paginated(query, page=page, page_size=page_size)

    # ------------------------------------------------------------ duplicates --
    async def get_by_hashed_content(self, org_id: str, hashed_content: str) -> Item | None:
        return await Item.find_one(
            {"org_id": org_id, "hashed_content": hashed_content, "is_duplicate": False}
        )

    async def list_by_file_size_range(
        self, org_id: str, min_size: int, max_size: int
    ) -> list[Item]:
        return await Item.find(
            Item.org_id == org_id, Item.file_size >= min_size, Item.file_size <= max_size
        ).to_list()

    async def has_duplicates(self, item_id: str) -> bool:
        return await self.exists({"duplicate_of": item_id, "is_duplicate": True})

    # ----------------------------------------------------------------- stats --
    async def count_by_status(self, org_id: str) -> dict[str, int]:
        """Example aggregation: ``{"active": 10, "pending": 2}``."""
        rows = await self.aggregate(
            [{"$match": {"org_id": org_id}}, {"$group": {"_id": "$status", "count": {"$sum": 1}}}]
        )
        return {r["_id"]: r["count"] for r in rows}

    async def added_in_last_days(self, org_id: str, days: int = 30) -> int:
        since = utcnow() - timedelta(days=days)
        return await self.count({"org_id": org_id, "created_at": {"$gte": since}})

    async def recent(self, org_id: str, limit: int = 5) -> list[Item]:
        docs, _ = await self.list_paginated(
            {"org_id": org_id}, page=1, page_size=limit, sort_by="-updated_at"
        )
        return docs
