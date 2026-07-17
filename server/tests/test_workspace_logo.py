"""Integration: brand logo upload/delete (Phase 4b). Mirrors the card-image
upload defenses (allow-listed type, size cap, server-derived key), stores the
result on `brand_profile.logo`, and serves it via the existing image route.
Demo users are blocked by `require_not_demo` before any mutation."""
from dataclasses import replace

import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
from app.main import app
from app.models.common import utcnow
from app.models.user import UserInDB
from app.services.storage_service import get_storage
from app.services.upload_service import IMAGE_POLICY
from app.utils.dependencies import get_current_user
from tests.conftest import TEST_DB_NAME

WORKSPACE_OID = ObjectId()
OWNER_OID = ObjectId()

# A minimal valid 1x1 PNG (bytes only — the route validates by extension/type).
PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000a49444154789c6360000002000154a24f3f0000000049454e44ae426082"
)


def _owner_user(is_demo: bool = False) -> UserInDB:
    return UserInDB(
        id=str(OWNER_OID),
        email="owner@example.com",
        hashed_password="x",
        full_name="Owner",
        is_demo=is_demo,
    )


async def _seed_workspace(test_db) -> None:
    now = utcnow()
    await test_db.workspaces.insert_one(
        {
            "_id": WORKSPACE_OID,
            "owner_id": OWNER_OID,
            "name": "Verdure",
            "slug": "verdure",
            "brand_profile": {"colors": [{"name": "Forest", "hex": "#1C3A2E", "role": "primary"}]},
            "vector_namespace": str(WORKSPACE_OID),
            "embedding_model": settings.embedding_model,
            "embedding_dim": settings.embedding_dim,
            "asset_count": 0,
            "ready_chunk_count": 0,
            "created_at": now,
            "updated_at": now,
        }
    )


def _logo_url() -> str:
    return f"/api/workspaces/{WORKSPACE_OID}/logo"


async def _make_client(test_db, tmp_path, monkeypatch, *, is_demo: bool) -> AsyncClient:
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    get_storage.cache_clear()
    await _seed_workspace(test_db)
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[get_current_user] = lambda: _owner_user(is_demo)
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest_asyncio.fixture
async def client(test_db, tmp_path, monkeypatch):
    ac = await _make_client(test_db, tmp_path, monkeypatch, is_demo=False)
    async with ac:
        yield ac
    app.dependency_overrides.clear()
    get_storage.cache_clear()


@pytest_asyncio.fixture
async def demo_client(test_db, tmp_path, monkeypatch):
    ac = await _make_client(test_db, tmp_path, monkeypatch, is_demo=True)
    async with ac:
        yield ac
    app.dependency_overrides.clear()
    get_storage.cache_clear()


@pytest.mark.asyncio
async def test_logo_upload_sets_brand_logo(client, test_db):
    resp = await client.post(
        _logo_url(), files={"file": ("logo.png", PNG_1x1, "image/png")}
    )
    assert resp.status_code == 200
    logo = resp.json()["brand_profile"]["logo"]
    assert logo is not None
    assert logo["storage_key"].startswith(f"{WORKSPACE_OID}/images/")
    assert logo["url"].startswith(f"/api/workspaces/{WORKSPACE_OID}/images/file/")

    # Persisted on the doc + bytes actually stored under the server-derived key.
    doc = await test_db.workspaces.find_one({"_id": WORKSPACE_OID})
    assert doc["brand_profile"]["logo"]["storage_key"] == logo["storage_key"]
    # The palette is untouched (targeted update, not a profile wipe).
    assert doc["brand_profile"]["colors"][0]["hex"] == "#1C3A2E"
    assert await get_storage().read(logo["storage_key"]) == PNG_1x1


@pytest.mark.asyncio
async def test_logo_upload_rejects_bad_type(client, test_db):
    resp = await client.post(
        _logo_url(), files={"file": ("logo.txt", b"hello", "text/plain")}
    )
    assert resp.status_code == 415
    doc = await test_db.workspaces.find_one({"_id": WORKSPACE_OID})
    assert doc["brand_profile"].get("logo") is None


@pytest.mark.asyncio
async def test_logo_upload_rejects_oversize(client, test_db, monkeypatch):
    monkeypatch.setattr("app.routes.workspaces.IMAGE_POLICY", replace(IMAGE_POLICY, max_bytes=4))
    resp = await client.post(
        _logo_url(), files={"file": ("logo.png", PNG_1x1, "image/png")}
    )
    assert resp.status_code == 413
    doc = await test_db.workspaces.find_one({"_id": WORKSPACE_OID})
    assert doc["brand_profile"].get("logo") is None


@pytest.mark.asyncio
async def test_logo_upload_rejects_empty(client):
    resp = await client.post(
        _logo_url(), files={"file": ("logo.png", b"", "image/png")}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_logo_upload_demo_blocked(demo_client, test_db):
    resp = await demo_client.post(
        _logo_url(), files={"file": ("logo.png", PNG_1x1, "image/png")}
    )
    assert resp.status_code == 403
    doc = await test_db.workspaces.find_one({"_id": WORKSPACE_OID})
    assert doc["brand_profile"].get("logo") is None


@pytest.mark.asyncio
async def test_logo_delete_unsets_and_removes_bytes(client, test_db):
    up = await client.post(_logo_url(), files={"file": ("logo.png", PNG_1x1, "image/png")})
    key = up.json()["brand_profile"]["logo"]["storage_key"]

    resp = await client.delete(_logo_url())
    assert resp.status_code == 200
    assert resp.json()["brand_profile"]["logo"] is None

    doc = await test_db.workspaces.find_one({"_id": WORKSPACE_OID})
    assert doc["brand_profile"]["logo"] is None
    with pytest.raises(FileNotFoundError):
        await get_storage().read(key)
