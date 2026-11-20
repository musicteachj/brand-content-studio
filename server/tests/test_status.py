from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from pydantic import SecretStr

from app.config import settings
from app.database import get_database
from app.main import app
from app.routes import status as status_route
from app.services.ai_ledger import BudgetSnapshot


@pytest.fixture(autouse=True)
def _fresh_cache():
    status_route.clear_status_cache()
    yield
    status_route.clear_status_cache()


@pytest_asyncio.fixture
async def client():
    app.dependency_overrides[get_database] = lambda: object()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c
    app.dependency_overrides.pop(get_database, None)


def _snapshot(monkeypatch, allowance, spent, calls):
    async def fake(db, *, now=None):
        calls.append(1)
        return BudgetSnapshot(allowance_today=allowance, spent_today=spent, left_this_month=1)

    monkeypatch.setattr(status_route, "budget_snapshot", fake)


async def test_budget_zero_is_off_and_never_reads_the_database(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_monthly_budget_usd", Decimal(0))
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "turnstile_site_key", "")
    monkeypatch.setattr(settings, "turnstile_secret_key", SecretStr(""))
    calls: list[int] = []
    _snapshot(monkeypatch, 0, 0, calls)
    r = await client.get("/api/status")
    assert r.json() == {
        "live_ai_available": False,
        "live_ai_reason": "off",
        "turnstile_site_key": "1x00000000000000000000AA",
        "password_login": True,
    }
    assert calls == []


async def test_room_under_60k_is_paused(client, monkeypatch):
    _snapshot(monkeypatch, 1_000_000, 940_001, [])
    r = await client.get("/api/status")
    assert r.json()["live_ai_available"] is False
    assert r.json()["live_ai_reason"] == "paused"


async def test_enough_room_is_available(client, monkeypatch):
    _snapshot(monkeypatch, 1_000_000, 940_000, [])
    r = await client.get("/api/status")
    assert r.json()["live_ai_available"] is True
    assert r.json()["live_ai_reason"] == "available"


async def test_a_second_call_within_30_seconds_does_not_read_the_database(client, monkeypatch):
    calls: list[int] = []
    _snapshot(monkeypatch, 1_000_000, 0, calls)
    await client.get("/api/status")
    r = await client.get("/api/status")
    assert len(calls) == 1
    assert r.json()["live_ai_available"] is True


async def test_the_cache_expires_after_30_seconds(client, monkeypatch):
    calls: list[int] = []
    _snapshot(monkeypatch, 1_000_000, 0, calls)
    clock = [1_000.0]
    monkeypatch.setattr(status_route.time, "monotonic", lambda: clock[0])
    await client.get("/api/status")
    clock[0] += 31
    await client.get("/api/status")
    assert len(calls) == 2


async def test_cache_control_header(client, monkeypatch):
    _snapshot(monkeypatch, 1_000_000, 0, [])
    r = await client.get("/api/status")
    assert r.headers["cache-control"] == "public, max-age=30"


async def test_development_with_blank_keys_shows_the_test_site_key(client, monkeypatch):
    _snapshot(monkeypatch, 1_000_000, 0, [])
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "turnstile_site_key", "")
    monkeypatch.setattr(settings, "turnstile_secret_key", SecretStr(""))
    body = (await client.get("/api/status")).json()
    assert body["turnstile_site_key"] == "1x00000000000000000000AA"
    assert body["password_login"] is True


async def test_production_closes_password_login_and_shows_the_real_site_key(client, monkeypatch):
    _snapshot(monkeypatch, 1_000_000, 0, [])
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "turnstile_site_key", "0x4AAAAAAAreal")
    monkeypatch.setattr(settings, "turnstile_secret_key", SecretStr("0x4AAAAAAAreal-secret"))
    body = (await client.get("/api/status")).json()
    assert body["turnstile_site_key"] == "0x4AAAAAAAreal"
    assert body["password_login"] is False
