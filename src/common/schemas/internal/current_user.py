"""
Authenticated user as resolved from the ``x-user-data`` header.

The API gateway / auth service authenticates the request and forwards the
user's claims as a JSON header. ``get_current_user`` parses it into this model.
Services receive ``CurrentUser`` and scope every query by ``user.org_id``.
"""

from pydantic import BaseModel

from src.common.enums.platform import Product
from src.common.enums.user_role import UserRole
from src.common.enums.user_status import UserStatus


class PlatformRoles(BaseModel):
    """Per-product role, for platforms that host several products."""

    product: Product
    role: UserRole


class CurrentUser(BaseModel):
    id: str
    org_id: str = ""
    role: UserRole = UserRole.USER
    user_status: UserStatus = UserStatus.ACTIVE
    username: str = ""
    email: str = ""
    email_cannonical: str = ""
    name: str = ""
    color: str | None = None
    platform_roles: list[PlatformRoles] = []

    def has_product_role(self, product: Product, *roles: UserRole) -> bool:
        """``user.has_product_role(Product.DEFAULT, UserRole.ADMIN)``"""
        return any(pr.product == product and pr.role in roles for pr in self.platform_roles)
