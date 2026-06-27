"""Phase 6 PR-B — reingest resets an errored asset (demo-blocked); the card-image
upload is demo-blocked, reconciling server with the UI."""
import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

import app.routes.assets as assets_routes
from app.config import settings
from app.database import get_database
from app.main import app
from app.models.common import utcnow
from app.models.user import UserInDB
from app.utils.dependencies import get_current_user, get_workspace_or_404
from tests.conftest import TEST_DB_NAME

WS = ObjectId()
OWNER = ObjectId()
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000a49444154789c6360000002000154a24f3f0000000049454e44ae426082"
)


def _user(is_demo: bool = False) -> UserInDB:
    return UserInDB(id=str(OWNER), email="o@example.com", hashed_password="x",
                    full_name="O", is_demo=is_demo)


def _workspace() -> dict:
    return {"_id": WS, "owner_id": OWNER, "vector_namespace": str(WS)}


async def _seed_errored_asset(db) -> str:
    oid = ObjectId()
    now = utcnow()
    await db.assets.insert_one({
        "_id": oid, "workspace_id": WS, "filename": "f.md", "content_type": "text/markdown",
        "asset_kind": "other", "storage_key": "k", "size_bytes": 1,
        "ingestion_status": "error", "chunk_count": 0, "error": "boom",
        "ingested_at": None, "created_at": now, "updated_at": now,
    })
    return str(oid)


async def _noop_ingest(asset_id: str, namespace: str) -> None:
    """Out-of-band ingestion is covered by test_ingestion.py; stub it here so the
    background task doesn't reach for an unconnected production DB after response."""
    return None


async def _mk(test_db, monkeypatch, *, is_demo=False) -> AsyncClient:
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    monkeypatch.setattr(assets_routes, "ingest_asset", _noop_ingest)
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[get_current_user] = lambda: _user(is_demo)
    app.dependency_overrides[get_workspace_or_404] = lambda: _workspace()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def client(test_db, monkeypatch):
    ac = await _mk(test_db, monkeypatch)
    async with ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_reingest_resets_to_processing(client, test_db):
    asset_id = await _seed_errored_asset(test_db)
    resp = await client.post(f"/api/workspaces/{WS}/assets/{asset_id}/reingest")
    assert resp.status_code == 202
    assert resp.json()["ingestion_status"] == "processing"
    doc = await test_db.assets.find_one({"_id": ObjectId(asset_id)})
    assert doc["ingestion_status"] == "processing"
    assert doc["error"] is None


@pytest.mark.asyncio
async def test_reingest_missing_is_404(client):
    resp = await client.post(f"/api/workspaces/{WS}/assets/{ObjectId()}/reingest")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reingest_demo_blocked(test_db, monkeypatch):
    asset_id = await _seed_errored_asset(test_db)
    ac = await _mk(test_db, monkeypatch, is_demo=True)
    async with ac:
        resp = await ac.post(f"/api/workspaces/{WS}/assets/{asset_id}/reingest")
    app.dependency_overrides.clear()
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_image_upload_demo_blocked(test_db, monkeypatch):
    ac = await _mk(test_db, monkeypatch, is_demo=True)
    async with ac:
        resp = await ac.post(
            f"/api/workspaces/{WS}/images/upload",
            files={"file": ("c.png", PNG, "image/png")},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 403
