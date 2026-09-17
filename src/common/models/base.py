"""
Base Beanie document every model inherits from.

Provides ``created_at`` / ``updated_at`` timestamps (UTC) and is the marker
class ``Database.connect()`` uses to auto-discover documents.

Define a model
--------------
    from typing import Optional
    from src.common.models.base import BaseDocument

    class Widget(BaseDocument):
        name: str
        org_id: str = ""            # multi-tenant scoping - always include
        uploaded_by: str = ""       # user id - for audit + ownership transfer
        status: WidgetStatus = WidgetStatus.ACTIVE
        metadata: Optional[dict] = None

        class Settings:
            name = "widgets"                    # collection name
            indexes = ["org_id", "uploaded_by"] # or pymongo IndexModel(...)

Timestamps update automatically on ``insert()`` and ``save()``. When using
``Model.find(...).update({"$set": {...}})`` remember to include
``updated_at`` yourself (see ``BaseRepository.update``).
"""

from datetime import UTC, datetime

from beanie import Document
from pydantic import Field


def utcnow() -> datetime:
    return datetime.now(UTC)


class BaseDocument(Document):
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime | None = None

    class Settings:
        # Subclasses MUST override ``name``.
        name = "base_collection"

    async def save(self, *args, **kwargs):
        self.updated_at = utcnow()
        return await super().save(*args, **kwargs)

    async def insert(self, *args, **kwargs):
        self.updated_at = utcnow()
        return await super().insert(*args, **kwargs)
