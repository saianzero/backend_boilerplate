"""Lifecycle of an Item. String enums serialise cleanly to JSON/Mongo."""

from enum import Enum


class ItemStatus(str, Enum):
    PENDING = "pending"  # created, file not processed yet
    PROCESSING = "processing"  # background task running
    ACTIVE = "active"  # processed successfully
    FAILED = "failed"  # background task failed
    ARCHIVED = "archived"
