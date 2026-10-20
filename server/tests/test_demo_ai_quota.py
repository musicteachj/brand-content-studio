"""One AI-call counter for the demo account (known-gaps plan, step 1). Every paid
model route consumes one unit of a per-account daily count, so the three routes
that save nothing (brand extract, template AI fill, fill from a document) are
capped too. Admission is one atomic write, so concurrency can't overshoot."""
import asyncio
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from bson import ObjectId
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

import app.database as database
from app.config import settings
from app.database import ensure_indexes, get_database
from app.main import app
from app.models.user import UserInDB
from app.services import usage_service
from app.utils.dependencies import enforce_demo_ai_quota, get_current_user, get_workspace_or_404
from tests.conftest import TEST_DB_NAME

DAY = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)


def _demo() -> UserInDB:
    return UserInDB(id=str(ObjectId()), email="demo@x.com", hashed_password="x", full_name="D", is_demo=True)


# --- the counter -------------------------------------------------------------
@pytest.mark.asyncio
async def test_admits_up_to_the_limit_then_refuses(test_db):
    uid = str(ObjectId())
    results = [await usage_service.consume_demo_ai_action(test_db, uid, 3, now=DAY) for _ in range(5)]
    assert results == [True, True, True, False, False]
    doc = await test_db.usage.find_one({"_id": f"{uid}:2026-10-20"})
    assert doc["count"] == 3
    assert doc["expires_at"] > DAY.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_concurrent_requests_cannot_overshoot(test_db):
    uid = str(ObjectId())
    results = await asyncio.gather(
        *(usage_service.consume_demo_ai_action(test_db, uid, 10, now=DAY) for _ in range(15))
    )
    assert results.count(True) == 10
    assert (await test_db.usage.find_one({"_id": f"{uid}:2026-10-20"}))["count"] == 10


@pytest.mark.asyncio
async def test_a_first_of_the_day_race_is_not_refused(test_db):
    # Several first requests race to create the day's document; a duplicate-key
    # loser must still be admitted while under the limit.
    uid = str(ObjectId())
    results = await asyncio.gather(
        *(usage_service.consume_demo_ai_action(test_db, uid, 50, now=DAY) for _ in range(8))
    )
    assert all(results)


@pytest.mark.asyncio
async def test_a_new_utc_day_starts_at_zero(test_db):
    uid = str(ObjectId())
    assert await usage_service.consume_demo_ai_action(test_db, uid, 1, now=DAY)
    assert not await usage_service.consume_demo_ai_action(test_db, uid, 1, now=DAY)
    tomorrow = DAY.replace(day=21, hour=0, minute=1)
    assert await usage_service.consume_demo_ai_action(test_db, uid, 1, now=tomorrow)


@pytest.mark.asyncio
async def test_a_zero_limit_admits_nothing(test_db):
    assert not await usage_service.consume_demo_ai_action(test_db, str(ObjectId()), 0, now=DAY)


@pytest.mark.asyncio
async def test_ensure_indexes_adds_a_ttl_index_on_usage(test_db, monkeypatch):
    monkeypatch.setattr(database.db, "client", test_db.client)
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    await ensure_indexes()
    info = await test_db.usage.index_information()
    ttl = [i for i in info.values() if i["key"] == [("expires_at", 1)]]
    assert ttl and ttl[0]["expireAfterSeconds"] == 0


# --- the dependency ------------------------------------------------------------
@pytest.mark.asyncio
async def test_demo_over_the_limit_gets_a_readable_429(test_db, monkeypatch):
    monkeypatch.setattr(settings, "demo_daily_generation_limit", 1)
    demo = _demo()
    await enforce_demo_ai_quota(current_user=demo, db=test_db)
    with pytest.raises(HTTPException) as exc:
        await enforce_demo_ai_quota(current_user=demo, db=test_db)
    assert exc.value.status_code == 429
    assert "daily limit" in exc.value.detail


@pytest.mark.asyncio
async def test_non_demo_users_are_never_counted():
    class _DB:
        usage = None  # would AttributeError if the quota touched it

    user = UserInDB(id=str(ObjectId()), email="u@x.com", hashed_password="x", full_name="U", is_demo=False)
    assert await enforce_demo_ai_quota(current_user=user, db=_DB()) is None


# --- wiring ----------------------------------------------------------------------
WS = str(ObjectId())
TPL = str(ObjectId())
PAID_ROUTES = [
    f"/api/workspaces/{WS}/generate/text",
    f"/api/workspaces/{WS}/generate/card",
    f"/api/workspaces/{WS}/generate/post",
    f"/api/workspaces/{WS}/generate/document",
    f"/api/workspaces/{WS}/brand/extract",
    f"/api/workspaces/{WS}/templates/{TPL}/ai-fill",
    f"/api/workspaces/{WS}/templates/{TPL}/fill-from-document",
]


class _NoDB:
    """Limit 0 and non-demo users never reach Mongo; touching it fails the test."""

    def __getattr__(self, name):
        raise AssertionError(f"the quota touched the database ({name})")


async def _client(db) -> AsyncClient:
    app.dependency_overrides[get_database] = lambda: db
    app.dependency_overrides[get_workspace_or_404] = lambda: {"_id": ObjectId(WS), "brand_profile": {}}
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def quota_client(monkeypatch):
    monkeypatch.setattr(settings, "demo_daily_generation_limit", 0)  # nothing left today
    async with await _client(_NoDB()) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", PAID_ROUTES)
async def test_every_paid_model_route_is_capped_for_the_demo(quota_client, path):
    app.dependency_overrides[get_current_user] = _demo
    resp = await quota_client.post(path)
    assert resp.status_code == 429, path
    assert "daily limit" in resp.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", PAID_ROUTES)
async def test_paid_routes_never_cap_a_non_demo_user(quota_client, path):
    app.dependency_overrides[get_current_user] = lambda: UserInDB(
        id=str(ObjectId()), email="u@x.com", hashed_password="x", full_name="U", is_demo=False
    )
    resp = await quota_client.post(path)  # no body: fails validation, never the quota
    assert resp.status_code != 429, path


@pytest.mark.asyncio
@pytest.mark.parametrize("path", PAID_ROUTES)
async def test_each_paid_route_charges_exactly_one_unit(test_db, monkeypatch, path):
    # Charged on admission (DECISIONS #35): even a request that then fails body
    # validation costs one unit, and never more than one.
    monkeypatch.setattr(settings, "demo_daily_generation_limit", 5)
    demo = _demo()
    app.dependency_overrides[get_current_user] = lambda: demo
    try:
        async with await _client(test_db) as ac:
            await ac.post(path)
    finally:
        app.dependency_overrides.clear()
    doc = await test_db.usage.find_one({"user_id": ObjectId(demo.id)})
    assert doc["count"] == 1, path


@pytest.mark.asyncio
async def test_ensure_indexes_drops_the_old_quota_index(test_db, monkeypatch):
    await test_db.generations.create_index([("owner_id", 1), ("created_at", -1)])
    monkeypatch.setattr(database.db, "client", test_db.client)
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    await ensure_indexes()
    assert "owner_id_1_created_at_-1" not in await test_db.generations.index_information()
    await ensure_indexes()  # idempotent once it's gone
