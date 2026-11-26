"""Liveness and readiness. Liveness never touches a database; readiness checks Mongo,
the vector store, and (when the seed runs at startup) the seed report, each with a
short timeout, and answers 503 when any of them fails."""
import asyncio
import time

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app import database
from app.config import settings
from app.database import get_database
from app.main import app
from app.routes import health as health_route
from seed.seed_demo import SeedReport
from tests.fakes import FakeVectorStore


class _Db:
    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay

    async def command(self, name: str) -> dict:
        await asyncio.sleep(self.delay)
        return {"ok": 1.0}


@pytest_asyncio.fixture
async def client(monkeypatch):
    monkeypatch.setattr(health_route, "get_vector_store", FakeVectorStore)
    monkeypatch.setattr(settings, "seed_on_startup", False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
    app.dependency_overrides.pop(get_database, None)


async def test_liveness_never_touches_the_database(client):
    def _no_database():
        raise AssertionError("liveness must not touch the database")

    app.dependency_overrides[get_database] = _no_database
    r = await client.get("/api/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_readiness_is_503_within_about_two_seconds_when_mongo_hangs(client):
    app.dependency_overrides[get_database] = lambda: _Db(delay=10)
    started = time.monotonic()
    r = await client.get("/api/health")
    elapsed = time.monotonic() - started
    assert r.status_code == 503
    assert r.json()["status"] == "unavailable"
    assert r.json()["mongo"] is False
    assert r.json()["vector_store"] is True
    assert elapsed < 3


async def test_readiness_is_200_when_everything_answers(client, monkeypatch):
    monkeypatch.setattr(settings, "seed_on_startup", True)
    monkeypatch.setattr(app.state, "seed_report", SeedReport(), raising=False)
    app.dependency_overrides[get_database] = lambda: _Db()
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "mongo": True, "vector_store": True, "seed": True}


async def test_readiness_is_503_when_the_seed_failed(client, monkeypatch):
    monkeypatch.setattr(settings, "seed_on_startup", True)
    monkeypatch.setattr(app.state, "seed_report", SeedReport(error="x"), raising=False)
    app.dependency_overrides[get_database] = lambda: _Db()
    r = await client.get("/api/health")
    assert r.status_code == 503
    assert r.json() == {
        "status": "unavailable",
        "mongo": True,
        "vector_store": True,
        "seed": False,
    }


async def test_readiness_is_503_when_the_vector_store_is_down(client, monkeypatch):
    class _DownStore(FakeVectorStore):
        async def health(self) -> bool:
            return False

    monkeypatch.setattr(health_route, "get_vector_store", _DownStore)
    app.dependency_overrides[get_database] = lambda: _Db()
    r = await client.get("/api/health")
    assert r.status_code == 503
    assert r.json()["vector_store"] is False


async def test_readiness_does_not_report_a_seed_it_never_ran(client):
    app.dependency_overrides[get_database] = lambda: _Db()
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["seed"] is None


async def test_the_mongo_client_is_bounded(monkeypatch):
    """A small pool, and timeouts so a lost server or a stalled socket can't hang a
    request (or the ledger's shielded writes) forever."""
    seen: dict = {}

    class _Admin:
        async def command(self, name: str) -> dict:
            return {"ok": 1.0}

    class _Client:
        admin = _Admin()

        def __init__(self, url: str, **kwargs) -> None:
            seen.update(kwargs)

        def close(self) -> None:
            return None

    monkeypatch.setattr(database, "AsyncIOMotorClient", _Client)
    monkeypatch.setattr(database.db, "client", None)
    await database.connect_to_mongo()
    assert seen == {
        "maxPoolSize": settings.mongo_max_pool_size,
        "serverSelectionTimeoutMS": 5000,
        "socketTimeoutMS": 20000,
    }
    assert settings.mongo_max_pool_size == 10
