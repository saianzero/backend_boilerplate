"""
Query parameters for ``GET /items/list``.

Every field becomes a query param via ``Depends()``. Add filters by adding
fields and mapping them in ``get_filters``.
"""

from datetime import date
from typing import ClassVar, Literal

from src.common.schemas.requests.pagination import ListRequestBase
from src.items.enums.item_status import ItemStatus


class ListItemsRequest(ListRequestBase):
    status: ItemStatus | None = None
    tag: str | None = None
    created_from: date | None = None
    created_to: date | None = None
    modified_from: date | None = None
    modified_to: date | None = None
    include_duplicates: bool = False
    sort_by: Literal["modified_date", "created_date", "name", "status"] | None = "modified_date"

    sort_map: ClassVar[dict[str, str]] = {
        "modified_date": "updated_at",
        "created_date": "created_at",
        "name": "name",
        "status": "status",
    }

    def get_filters(self) -> dict:
        filters: dict = {}
        if self.status:
            filters["status"] = self.status.value
        if self.tag:
            filters["tags"] = self.tag  # matches arrays containing the tag
        if not self.include_duplicates:
            filters["is_duplicate"] = False
        filters.update(self.date_range("created_at", self.created_from, self.created_to))
        filters.update(self.date_range("updated_at", self.modified_from, self.modified_to))
        return filters
