"""
Service tests: real repository on in-memory Mongo, mocked AWS + task queue.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.items.enums.item_status import ItemStatus
from src.items.repositories.item_repository import ItemRepository
from src.items.schemas.requests.create_item import (
    CreateItemRequest,
    PresignRequest,
    UploadedItemRequest,
)
from src.items.schemas.requests.list_items import ListItemsRequest
from src.items.schemas.requests.update_item import UpdateItemRequest
from src.items.services.item_service import ItemService


@pytest.fixture
def aws():
    m = MagicMock()
    m.generate_presigned_put_url.return_value = "https://s3/put"
    m.get_presigned_url.return_value = "https://s3/get"
    m.delete_object.return_value = True
    return m


@pytest.fixture
def service(aws) -> ItemService:
    return ItemService(item_repository=ItemRepository(), aws_utils=aws)


async def test_create(test_db, service, user):
    out = await service.create(CreateItemRequest(name="Doc", tags=["a"]), user)
    assert out["id"] and out["org_id"] == "org_1" and out["status"] == ItemStatus.ACTIVE


async def test_get_forbidden_for_other_org(test_db, service, user, other_org_user):
    created = await service.create(CreateItemRequest(name="Doc"), user)
    with pytest.raises(HTTPException) as exc:
        await service.get(created["id"], other_org_user)
    assert exc.value.status_code == 403


async def test_get_returns_presigned_url_when_file(test_db, service, user, aws):
    created = await service.create(CreateItemRequest(name="Doc"), user)
    await service.repo.update(created["id"], {"aws_object_name": "k"})
    out = await service.get(created["id"], user)
    assert out["file_url"] == "https://s3/get"
    aws.get_presigned_url.assert_called_once_with("k")


async def test_list_filters_and_pagination(test_db, service, user, sample_items):
    page = await service.list(ListItemsRequest(page=1, page_size=10, tag="finance"), user)
    assert page.total == 1 and page.data[0]["name"] == "Alpha report"


async def test_update_rejects_empty(test_db, service, user):
    created = await service.create(CreateItemRequest(name="Doc"), user)
    with pytest.raises(HTTPException) as exc:
        await service.update(created["id"], UpdateItemRequest(), user)
    assert exc.value.status_code == 400
    out = await service.update(created["id"], UpdateItemRequest(name="New"), user)
    assert out["name"] == "New"


async def test_presign_uploads(test_db, service, user, aws):
    out = await service.presign_uploads(
        [PresignRequest(file_name="a.pdf", file_type="application/pdf", file_size=10)], user
    )
    assert out[0]["upload_url"] == "https://s3/put"
    assert out[0]["aws_object_name"].startswith("org_1/items/")


async def test_create_from_uploads_queues_tasks(test_db, service, user):
    uploads = [
        UploadedItemRequest(
            file_data=PresignRequest(file_name="a.pdf", file_type="application/pdf", file_size=10),
            aws_object_name="org_1/items/x_a.pdf",
        )
    ]
    with (
        patch("src.common.utils.job_tracker.JobTracker.create", AsyncMock(return_value="job1")),
        patch("src.common.utils.job_tracker.JobTracker.mark", AsyncMock()) as mark,
        patch("src.items.tasks.process_item_task") as task,
    ):
        task.kiq = AsyncMock()
        out = await service.create_from_uploads(uploads, user)

    assert out["job_id"] == "job1" and out["total"] == 1 and len(out["items"]) == 1
    task.kiq.assert_awaited_once()
    mark.assert_awaited()
    stored = await service.repo.get_by_id(out["items"][0]["id"])
    assert stored.status == ItemStatus.PENDING and stored.aws_object_name == "org_1/items/x_a.pdf"


async def test_delete_blocks_original_with_duplicates(test_db, service, user):
    original = await service.create(CreateItemRequest(name="Orig"), user)
    dup = await service.create(CreateItemRequest(name="Dup"), user)
    await service.repo.update(dup["id"], {"is_duplicate": True, "duplicate_of": original["id"]})
    with pytest.raises(HTTPException) as exc:
        await service.delete(original["id"], user)
    assert exc.value.status_code == 409
    assert (await service.delete(dup["id"], user))["id"] == dup["id"]
    assert (await service.delete(original["id"], user))["id"] == original["id"]


async def test_bulk_delete_only_own_org(test_db, service, admin_user, sample_items, aws):
    ids = [str(d.id) for d in sample_items]
    out = await service.bulk_delete(ids, admin_user)
    assert out["deleted_count"] == 2 and out["not_deleted_ids"] == []
