"""Response shapes for the items API."""

from pydantic import BaseModel

from src.items.enums.item_status import ItemStatus


class ItemResponse(BaseModel):
    id: str
    name: str
    description: str = ""
    status: ItemStatus
    tags: list[str] = []
    org_id: str
    uploaded_by: str
    file_name: str | None = None
    file_type: str | None = None
    file_size: int | None = None
    is_duplicate: bool = False
    metadata: dict | None = None
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    file_url: str | None = None  # presigned GET url, only on detail endpoints


class PresignResponse(BaseModel):
    file_name: str
    file_type: str
    file_size: int
    aws_object_name: str
    upload_url: str


class QueuedItemsResponse(BaseModel):
    job_id: str
    total: int
    status: str
    items: list[dict]
