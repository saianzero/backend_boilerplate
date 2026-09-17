"""Products hosted by the platform. Extend as you add products."""

from enum import Enum


class Product(str, Enum):
    DEFAULT = "default"
