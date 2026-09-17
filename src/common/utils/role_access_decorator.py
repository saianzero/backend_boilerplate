"""
Role-based access dependency.

    from src.common.utils.role_access_decorator import access_roles
    from src.common.enums.user_role import UserRole

    @router.delete("/{id}")
    async def delete(id: str, user=Depends(access_roles([UserRole.ADMIN, UserRole.SUPERADMIN]))):
        ...

Returns the ``CurrentUser`` when allowed, raises 403 otherwise.
"""

from fastapi import Depends, HTTPException

from src.common.schemas.internal.current_user import CurrentUser

from .get_current_user import get_current_user


def access_roles(allowed_roles: list):
    async def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Permission denied")
        return user

    return checker
