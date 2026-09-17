"""
JSON-safe serialisation helpers.

    convert_object_ids(doc.model_dump())   # ObjectId -> str, recursively
    serialize_document(doc)                # model_dump + "id" as str
"""

from typing import Any

from beanie import PydanticObjectId
from bson import ObjectId


def convert_object_ids(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: convert_object_ids(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_object_ids(i) for i in obj]
    if isinstance(obj, (PydanticObjectId, ObjectId)):
        return str(obj)
    return obj


def serialize_document(doc) -> dict:
    """Beanie document -> plain dict with string ``id`` (drops ``revision_id``)."""
    data = doc.model_dump()
    data["id"] = str(doc.id)
    data.pop("revision_id", None)
    return convert_object_ids(data)
