"""Repository tests run against in-memory Mongo (mongomock-motor)."""

import pytest

from src.items.enums.item_status import ItemStatus
from src.items.models.item import Item
from src.items.repositories.item_repository import ItemRepository


@pytest.fixture
def repo() -> ItemRepository:
    return ItemRepository()


async def test_create_and_get(test_db, repo):
    item = await repo.create(Item(name="x", org_id="org_1", uploaded_by="u"))
    fetched = await repo.get_by_id(str(item.id))
    assert fetched is not None
    assert fetched.name == "x"
    assert fetched.created_at is not None and fetched.updated_at is not None


async def test_get_by_id_invalid_returns_none(test_db, repo):
    assert await repo.get_by_id("not-an-id") is None


async def test_list_paginated_and_sort(test_db, repo, sample_items):
    docs, total = await repo.list_paginated(
        {"org_id": "org_1"}, page=1, page_size=1, sort_by="name"
    )
    assert total == 2
    assert [d.name for d in docs] == ["Alpha report"]
    docs, _ = await repo.list_paginated({"org_id": "org_1"}, page=2, page_size=1, sort_by="name")
    assert [d.name for d in docs] == ["Beta notes"]


async def test_search_scoped_to_org(test_db, repo, sample_items):
    docs, total = await repo.search("report", "org_1", 1, 10)
    assert total == 1 and docs[0].name == "Alpha report"
    _, total = await repo.search("Gamma", "org_1", 1, 10)
    assert total == 0


async def test_update_sets_updated_at(test_db, repo, sample_items):
    item = sample_items[0]
    before = item.updated_at
    updated = await repo.update(str(item.id), {"status": ItemStatus.ARCHIVED.value})
    assert updated.status == ItemStatus.ARCHIVED
    # Mongo stores naive UTC datetimes at millisecond precision; normalise before comparing.
    assert updated.updated_at.replace(tzinfo=None) >= before.replace(tzinfo=None, microsecond=0)


async def test_delete_respects_org(test_db, repo, sample_items):
    item = sample_items[0]
    assert await repo.delete(str(item.id), org_id="org_2") is False
    assert await repo.delete(str(item.id), org_id="org_1") is True
    assert await repo.get_by_id(str(item.id)) is None


async def test_delete_many_and_count(test_db, repo, sample_items):
    ids = [str(d.id) for d in sample_items]
    deleted = await repo.delete_many(ids, org_id="org_1")
    assert deleted == 2
    assert await repo.count({"org_id": "org_2"}) == 1


async def test_count_by_status(test_db, repo, sample_items):
    await repo.update(str(sample_items[0].id), {"status": ItemStatus.ACTIVE.value})
    counts = await repo.count_by_status("org_1")
    assert counts == {"active": 1, "pending": 1}
