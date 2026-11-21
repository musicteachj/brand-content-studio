"""SEC-02: per-IP rate limiting on auth/generation.

The limiter is disabled globally for the suite (conftest); these tests re-enable
it around themselves with the shared `enabled_limiter` fixture.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import TURNSTILE_PASS_SECRET
from app.database import get_database
from app.main import app
from app.services.turnstile import DUMMY_TOKEN, TestKeyVerifier, get_turnstile_verifier
from app.utils.errors import RATE_LIMITED_COPY
from app.utils.ratelimit import AUTH_RATE_LIMIT

# A demo start that passes the bot check, so each request reaches the handler.
START = {"turnstile_token": DUMMY_TOKEN}


class _FakeUsers:
    async def find_one(self, _query):
        return None  # no demo user → 503, but the request still counts toward the limit


class _FakeDB:
    users = _FakeUsers()


def _override() -> None:
    app.dependency_overrides[get_database] = lambda: _FakeDB()
    app.dependency_overrides[get_turnstile_verifier] = lambda: TestKeyVerifier(TURNSTILE_PASS_SECRET)


@pytest.mark.asyncio
async def test_auth_endpoint_is_rate_limited(enabled_limiter):
    """The (limit+1)th auth request from one IP is rejected with 429."""
    _override()
    per_min = int(AUTH_RATE_LIMIT.split("/")[0])
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            statuses = [(await ac.post("/api/auth/demo-login", json=START)).status_code for _ in range(per_min + 1)]
    finally:
        app.dependency_overrides.clear()
    assert statuses[-1] == 429
    assert statuses.count(429) == 1  # only the over-limit request is blocked
    assert set(statuses[:-1]) == {503}  # the rest reach the handler (no demo user seeded)


@pytest.mark.asyncio
async def test_a_rate_limited_request_reads_plainly(enabled_limiter):
    """The 429 carries friendly copy and a code the client can show, not slowapi's
    `{"error": "Rate limit exceeded: ..."}`."""
    _override()
    per_min = int(AUTH_RATE_LIMIT.split("/")[0])
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            for _ in range(per_min):
                await ac.post("/api/auth/demo-login", json=START)
            resp = await ac.post("/api/auth/demo-login", json=START)
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 429
    assert resp.json() == {"detail": RATE_LIMITED_COPY, "code": "rate_limited"}


# Spend on the paid AI routes is bounded by the AI dollar ledger, covered in
# test_ai_routes_budget.py.
