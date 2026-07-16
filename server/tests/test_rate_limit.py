"""SEC-02: per-IP rate limiting on auth/generation, and the demo daily quota.

The limiter is disabled globally for the suite (conftest); these tests re-enable
it around themselves.
"""
import pytest
from bson import ObjectId
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
from app.main import app
from app.models.user import UserInDB
from app.utils.dependencies import enforce_demo_generation_quota
from app.utils.ratelimit import AUTH_RATE_LIMIT, limiter


class _FakeUsers:
    async def find_one(self, _query):
        return None  # no demo user → 404, but the request still counts toward the limit


class _FakeDB:
    users = _FakeUsers()


@pytest.fixture
def enabled_limiter():
    limiter.reset()
    limiter.enabled = True
    yield
    limiter.enabled = False
    limiter.reset()


@pytest.mark.asyncio
async def test_auth_endpoint_is_rate_limited(enabled_limiter):
    """The (limit+1)th auth request from one IP is rejected with 429."""
    app.dependency_overrides[get_database] = lambda: _FakeDB()
    per_min = int(AUTH_RATE_LIMIT.split("/")[0])
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            statuses = [(await ac.post("/api/auth/demo-login")).status_code for _ in range(per_min + 1)]
    finally:
        app.dependency_overrides.clear()
    assert statuses[-1] == 429
    assert statuses.count(429) == 1  # only the over-limit request is blocked
    assert set(statuses[:-1]) == {404}  # the rest reach the handler (no demo user seeded)


@pytest.mark.asyncio
async def test_demo_generation_quota_blocks_at_limit(monkeypatch):
    monkeypatch.setattr(settings, "demo_daily_generation_limit", 3)

    class _Gens:
        async def count_documents(self, _query):
            return 3  # already at the cap

    class _DB:
        generations = _Gens()

    demo = UserInDB(id=str(ObjectId()), email="d@x.com", hashed_password="x", full_name="D", is_demo=True)
    with pytest.raises(HTTPException) as exc:
        await enforce_demo_generation_quota(current_user=demo, db=_DB())
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_non_demo_user_bypasses_quota_without_a_db_hit():
    class _DB:
        generations = None  # would AttributeError if the quota touched it

    user = UserInDB(id=str(ObjectId()), email="u@x.com", hashed_password="x", full_name="U", is_demo=False)
    # Returns without raising and without querying the db.
    assert await enforce_demo_generation_quota(current_user=user, db=_DB()) is None
