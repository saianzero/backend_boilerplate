"""
Cross-cutting routes: current user, global search, user lookup.
"""

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query

from src.common.schemas.internal.current_user import CurrentUser
from src.common.services.common_service import CommonService
from src.common.utils.get_current_user import get_current_user
from src.core.container import Container

router = APIRouter(prefix="", tags=["common"])


@router.get("/get-user")
async def get_user(user: CurrentUser = Depends(get_current_user)):
    """Echo the user resolved from ``x-user-data``. Handy for debugging auth."""
    return user.model_dump()


@router.get("/global-search")
@inject
async def global_search(
    q: str = Query(..., min_length=1, description="Keyword to search across modules"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
    service: CommonService = Depends(Provide[Container.common_service]),
):
    return await service.global_search(q, user, page, page_size)


@router.get("/get-username-by-search")
@inject
async def get_usernames(
    q: str = Query(..., min_length=2),
    user: CurrentUser = Depends(get_current_user),
    service: CommonService = Depends(Provide[Container.common_service]),
):
    users = await service.get_usernames(q, user.org_id)
    return [{"_id": u.get("_id", u.get("id", "")), "name": u.get("name", "")} for u in users]
