from enum import Enum


class UserRole(str, Enum):
    SUPERADMIN = "Superadmin"
    ADMIN = "Admin"
    USER = "User"
