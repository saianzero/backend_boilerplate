"""PATCH-style update: only provided fields change."""

from pydantic import BaseModel

from src.items.enums.item_status import ItemStatus


class UpdateItemRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: ItemStatus | None = None
    tags: list[str] | None = None
    metadata: dict | None = None

    def changed_fields(self) -> dict:
        return self.model_dump(exclude_none=True)
