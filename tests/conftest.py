"""
Shared pytest fixtures.

- ``test_db``      : in-memory Mongo via ``mongomock-motor`` + Beanie init. No
                     external services needed. Fresh per test.
- ``user`` / ``admin_user`` : ``CurrentUser`` instances for service calls.
- ``user_headers`` : ``x-user-data`` header for HTTP tests.
- ``client``       : ``httpx.AsyncClient`` against a test app with the real
                     router + DI container, but with services you can override.

Override a provider in a test:
    container.item_service.override(providers.Object(mock_service))
"""

import json
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from beanie import init_beanie
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from src.common.enums.user_role import UserRole
from src.common.models.file import File
from src.common.schemas.internal.current_user import CurrentUser
from src.core.container import Container
from src.items.models.item import Item
from src.items.router import router as items_router

# Every Beanie document used by tests.
DOCUMENT_MODELS = [Item, File]


@pytest_asyncio.fixture(scope="function")
async def test_db() -> AsyncGenerator:
    client = AsyncMongoMockClient()
    database = client["test_db"]
    await init_beanie(database=database, document_models=DOCUMENT_MODELS)
    yield database
    client.close()


@pytest.fixture
def user() -> CurrentUser:
    return CurrentUser(
        id="user_1", org_id="org_1", role=UserRole.USER, email="u@example.com", name="User One"
    )


@pytest.fixture
def admin_user() -> CurrentUser:
    return CurrentUser(
        id="admin_1", org_id="org_1", role=UserRole.ADMIN, email="a@example.com", name="Admin"
    )


@pytest.fixture
def other_org_user() -> CurrentUser:
    return CurrentUser(id="user_2", org_id="org_2", role=UserRole.USER)


def headers_for(u: CurrentUser) -> dict:
    return {
        "x-user-data": json.dumps(
            {
                "user_id": u.id,
                "org_id": u.org_id,
                "role": u.role.value,
                "email": u.email,
                "name": u.name,
            }
        )
    }


@pytest.fixture
def user_headers(user) -> dict:
    return headers_for(user)


@pytest.fixture
def admin_headers(admin_user) -> dict:
    return headers_for(admin_user)


@pytest.fixture
def container():
    c = Container()
    c.wire(modules=["src.items.router"])
    yield c
    c.unwire()


@pytest_asyncio.fixture
async def client(container) -> AsyncGenerator[AsyncClient, None]:
    app = FastAPI()
    app.include_router(items_router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def sample_items(test_db) -> list[Item]:
    docs = [
        Item(
            name="Alpha report",
            description="quarterly numbers",
            tags=["finance"],
            org_id="org_1",
            uploaded_by="user_1",
        ),
        Item(
            name="Beta notes",
            description="meeting",
            tags=["ops"],
            org_id="org_1",
            uploaded_by="user_1",
        ),
        Item(name="Gamma", description="other org", org_id="org_2", uploaded_by="user_2"),
    ]
    for d in docs:
        await d.insert()
    return docs
