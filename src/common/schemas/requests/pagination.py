"""
Reusable request schemas for list endpoints.

``PaginationParams`` alone gives you ``?page=&page_size=``. Subclass
``ListRequestBase`` to add filters and sorting with a consistent shape:

    class ListWidgetsRequest(ListRequestBase):
        status: Optional[WidgetStatus] = None
        created_from: Optional[date] = None
        created_to: Optional[date] = None
        sort_by: Literal["created_date", "modified_date", "name"] = "modified_date"

        sort_map = {"created_date": "created_at", "modified_date": "updated_at", "name": "name"}

        def get_filters(self) -> dict:
            f = {}
            if self.status:
                f["status"] = self.status
            f.update(self.date_range("created_at", self.created_from, self.created_to))
            return f

Use it in a router with ``request: ListWidgetsRequest = Depends()`` so every
field becomes a query parameter.
"""

from datetime import UTC, date, datetime, time
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    page: int = Field(1, ge=1, description="1-based page number")
    page_size: int = Field(10, ge=1, le=100, description="Items per page")

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.page_size


class ListRequestBase(PaginationParams):
    sort_by: str | None = "modified_date"
    sort_order: Literal["asc", "desc"] = "desc"

    #: API sort key -> Mongo field. Override in subclass.
    sort_map: ClassVar[dict[str, str]] = {
        "created_date": "created_at",
        "modified_date": "updated_at",
    }

    def get_filters(self) -> dict[str, Any]:
        """Override to translate request fields into a Mongo filter dict."""
        return {}

    def get_sort(self) -> str:
        field = self.sort_map.get(self.sort_by or "", "updated_at")
        return f"{'' if self.sort_order == 'asc' else '-'}{field}"

    @staticmethod
    def date_range(field: str, start: date | None, end: date | None) -> dict[str, Any]:
        """Build ``{field: {"$gte": ..., "$lte": ...}}`` from optional dates."""
        rng: dict[str, Any] = {}
        if start:
            rng["$gte"] = datetime.combine(start, time.min, tzinfo=UTC)
        if end:
            rng["$lte"] = datetime.combine(end, time.max, tzinfo=UTC)
        return {field: rng} if rng else {}


class BulkIdsRequest(BaseModel):
    """Body for bulk operations: ``{"ids": ["...", "..."]}``."""

    ids: list[str] = Field(..., min_length=1)
