"""
HTTP layer for items. Routers only: parse input, resolve user, call service.

Every route:
- is scoped to the caller's org via ``get_current_user``;
- receives its service from the DI container (``@inject`` + ``Provide``);
- returns plain dicts / pydantic models (FastAPI serialises them).

Mount in ``main.py`` with ``app.include_router(items_router)`` and add
``"src.items.router"`` to ``container.wire(modules=[...])``.
"""

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query

from src.common.enums.user_role import UserRole
from src.common.schemas.internal.current_user import CurrentUser
from src.common.schemas.requests.pagination import BulkIdsRequest
from src.common.utils.get_current_user import get_current_user
from src.common.utils.role_access_decorator import access_roles
from src.core.container import Container
from src.items.schemas.requests.create_item import (
    CreateItemRequest,
    PresignRequest,
    UploadedItemRequest,
)
from src.items.schemas.requests.list_items import ListItemsRequest
from src.items.schemas.requests.update_item import UpdateItemRequest
from src.items.services.item_service import ItemService

router = APIRouter(prefix="/items", tags=["items"])


# --------------------------------------------------------------------- create --
@router.post("/create")
@inject
async def create_item(
    request: CreateItemRequest,
    user: CurrentUser = Depends(get_current_user),
    service: ItemService = Depends(Provide[Container.item_service]),
):
    """Create an item from JSON (no file)."""
    return await service.create(request, user)


@router.post("/generate-presigned-url")
@inject
async def generate_presigned_urls(
    files: list[PresignRequest],
    user: CurrentUser = Depends(get_current_user),
    service: ItemService = Depends(Provide[Container.item_service]),
):
    """Upload step 1: returns a PUT url per file; the browser uploads directly to S3."""
    return await service.presign_uploads(files, user)


@router.post("/process-uploaded")
@inject
async def process_uploaded(
    uploads: list[UploadedItemRequest],
    user: CurrentUser = Depends(get_current_user),
    service: ItemService = Depends(Provide[Container.item_service]),
):
    """Upload step 2: create items for uploaded objects and queue background processing."""
    return await service.create_from_uploads(uploads, user)


@router.post("/reprocess")
@inject
async def reprocess_items(
    request: BulkIdsRequest,
    user: CurrentUser = Depends(get_current_user),
    service: ItemService = Depends(Provide[Container.item_service]),
):
    return await service.reprocess(request.ids, user)


@router.get("/job-status/{job_id}")
@inject
async def job_status(
    job_id: str,
    user: CurrentUser = Depends(get_current_user),
    service: ItemService = Depends(Provide[Container.item_service]),
):
    """Poll progress of a ``process-uploaded`` / ``reprocess`` batch."""
    return await service.job_status(job_id, user)


# ----------------------------------------------------------------------- read --
@router.get("/list")
@inject
async def list_items(
    request: ListItemsRequest = Depends(),
    user: CurrentUser = Depends(get_current_user),
    service: ItemService = Depends(Provide[Container.item_service]),
):
    """Paginated, filterable, sortable list. All ``ListItemsRequest`` fields are query params."""
    return await service.list(request, user)


@router.get("/search")
@inject
async def search_items(
    q: str = Query(..., min_length=1, description="Keyword"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
    service: ItemService = Depends(Provide[Container.item_service]),
):
    return await service.search(q, user, page, page_size)


@router.get("/stats")
@inject
async def item_stats(
    user: CurrentUser = Depends(get_current_user),
    service: ItemService = Depends(Provide[Container.item_service]),
):
    return await service.stats(user)


@router.get("/get/{item_id}")
@inject
async def get_item(
    item_id: str,
    user: CurrentUser = Depends(get_current_user),
    service: ItemService = Depends(Provide[Container.item_service]),
):
    """Single item, includes a presigned ``file_url`` when a file is attached."""
    return await service.get(item_id, user)


# --------------------------------------------------------------------- update --
@router.put("/update/{item_id}")
@inject
async def update_item(
    item_id: str,
    request: UpdateItemRequest,
    user: CurrentUser = Depends(get_current_user),
    service: ItemService = Depends(Provide[Container.item_service]),
):
    return await service.update(item_id, request, user)


# --------------------------------------------------------------------- delete --
@router.delete("/delete/{item_id}")
@inject
async def delete_item(
    item_id: str,
    user: CurrentUser = Depends(get_current_user),
    service: ItemService = Depends(Provide[Container.item_service]),
):
    return await service.delete(item_id, user)


@router.post("/bulk-delete")
@inject
async def bulk_delete_items(
    request: BulkIdsRequest,
    # Example of role gating: only admins may bulk delete.
    user: CurrentUser = Depends(access_roles([UserRole.ADMIN, UserRole.SUPERADMIN])),
    service: ItemService = Depends(Provide[Container.item_service]),
):
    return await service.bulk_delete(request.ids, user)
