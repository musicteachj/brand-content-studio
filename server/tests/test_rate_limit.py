"""SEC-02: per-IP rate limiting on auth/generation.

The limiter is disabled globally for the suite (conftest); these tests re-enable
it around themselves.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_database
from app.main import app
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


# The demo daily quota itself (a per-account AI-call counter) is covered in
# test_demo_ai_quota.py.
