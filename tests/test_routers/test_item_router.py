"""
Router tests: HTTP layer only. The service is replaced through the DI
container so no database or queue is touched.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from dependency_injector import providers


@pytest.fixture
def mock_service(container):
    svc = MagicMock()
    for name in (
        "create",
        "get",
        "list",
        "search",
        "stats",
        "update",
        "delete",
        "bulk_delete",
        "presign_uploads",
        "create_from_uploads",
        "reprocess",
        "job_status",
    ):
        setattr(svc, name, AsyncMock())
    container.item_service.override(providers.Object(svc))
    yield svc
    container.item_service.reset_override()


async def test_missing_user_header_is_422(client, mock_service):
    r = await client.get("/items/list")
    assert r.status_code == 422


async def test_bad_user_header_is_400(client, mock_service):
    r = await client.get("/items/list", headers={"x-user-data": "not-json"})
    assert r.status_code == 400


async def test_list_passes_query_params(client, mock_service, user_headers):
    mock_service.list.return_value = {
        "total": 0,
        "page": 2,
        "page_size": 5,
        "total_pages": 0,
        "data": [],
    }
    r = await client.get(
        "/items/list?page=2&page_size=5&status=active&sort_by=name&sort_order=asc",
        headers=user_headers,
    )
    assert r.status_code == 200
    req, user = mock_service.list.await_args.args
    assert req.page == 2 and req.page_size == 5 and req.get_sort() == "name"
    assert req.get_filters()["status"] == "active"
    assert user.org_id == "org_1"


async def test_create(client, mock_service, user_headers):
    mock_service.create.return_value = {"id": "1", "name": "Doc"}
    r = await client.post("/items/create", json={"name": "Doc"}, headers=user_headers)
    assert r.status_code == 200 and r.json()["id"] == "1"


async def test_create_validation(client, mock_service, user_headers):
    r = await client.post("/items/create", json={"name": ""}, headers=user_headers)
    assert r.status_code == 422


async def test_get(client, mock_service, user_headers):
    mock_service.get.return_value = {"id": "abc"}
    r = await client.get("/items/get/abc", headers=user_headers)
    assert r.status_code == 200
    assert mock_service.get.await_args.args[0] == "abc"


async def test_bulk_delete_requires_admin(client, mock_service, user_headers, admin_headers):
    r = await client.post("/items/bulk-delete", json={"ids": ["a"]}, headers=user_headers)
    assert r.status_code == 403
    mock_service.bulk_delete.return_value = {
        "message": "ok",
        "deleted_count": 1,
        "not_deleted_ids": [],
    }
    r = await client.post("/items/bulk-delete", json={"ids": ["a"]}, headers=admin_headers)
    assert r.status_code == 200


async def test_search_requires_q(client, mock_service, user_headers):
    r = await client.get("/items/search", headers=user_headers)
    assert r.status_code == 422
    mock_service.search.return_value = {"total": 0, "data": []}
    r = await client.get("/items/search?q=x", headers=user_headers)
    assert r.status_code == 200
