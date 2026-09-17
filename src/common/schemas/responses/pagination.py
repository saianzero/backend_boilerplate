"""
Standard envelope for paginated list responses.

    return PaginatedResponse.build(items=[w.model_dump() for w in docs], total=total,
                                   page=req.page, page_size=req.page_size)
"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    total: int
    page: int
    page_size: int
    total_pages: int
    data: list[T]

    @classmethod
    def build(cls, items: list[Any], total: int, page: int, page_size: int):
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return cls(total=total, page=page, page_size=page_size, total_pages=total_pages, data=items)


class MessageResponse(BaseModel):
    message: str


class BulkDeleteResponse(BaseModel):
    message: str
    deleted_count: int
    not_deleted_ids: list[str] = []
