"""Custom card presets: model + service + routes (Phase 5 PR-B)."""
import asyncio

import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
from app.main import app
from app.models.common import BrandProfile, CardPreset, utcnow
from app.models.user import UserInDB
from app.services.workspace_service import (
    MAX_CARD_PRESETS,
    WorkspaceWriteConflict,
    add_workspace_card_preset,
    remove_workspace_card_preset,
)
from app.utils.dependencies import get_current_user
from tests.conftest import TEST_DB_NAME


def test_card_presets_default_empty():
    assert BrandProfile().card_presets == []


def test_card_preset_shape():
    p = CardPreset(id="p1", name="Bold quote", template_id="quote", accent_hex="#1C3A2E")
    assert p.name == "Bold quote"
    assert p.template_id.value == "quote"


def test_card_preset_rejects_bad_hex():
    with pytest.raises(ValueError):
        CardPreset(id="p1", name="X", template_id="quote", accent_hex="not-a-hex")


WS = ObjectId()
OWNER = ObjectId()


def _user(is_demo=False, owner=OWNER):
    return UserInDB(id=str(owner), email="o@e.com", hashed_password="x", full_name="O",
                    is_demo=is_demo)


async def _seed(db, presets=None):
    await db.workspaces.insert_one({
        "_id": WS, "owner_id": OWNER, "name": "V", "slug": "v",
        "brand_profile": {"card_presets": presets or []}, "vector_namespace": str(WS),
        "embedding_model": settings.embedding_model, "embedding_dim": settings.embedding_dim,
        "asset_count": 0, "ready_chunk_count": 0, "created_at": utcnow(), "updated_at": utcnow(),
    })


async def _mk(test_db, tmp_path, monkeypatch, *, is_demo=False, owner=OWNER, presets=None):
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    await _seed(test_db, presets)
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[get_current_user] = lambda: _user(is_demo, owner)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _url():
    return f"/api/workspaces/{WS}/card-presets"


@pytest_asyncio.fixture
async def pc(test_db, tmp_path, monkeypatch):
    ac = await _mk(test_db, tmp_path, monkeypatch)
    async with ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_add_preset_appends(pc):
    resp = await pc.post(_url(), json={"name": "Bold quote", "template_id": "quote",
                                       "accent_hex": "#1C3A2E"})
    assert resp.status_code == 200
    presets = resp.json()["brand_profile"]["card_presets"]
    assert presets[0]["name"] == "Bold quote"
    assert presets[0]["template_id"] == "quote"
    assert presets[0]["accent_hex"] == "#1C3A2E"
    assert presets[0]["id"]


@pytest.mark.asyncio
async def test_add_preset_rejects_blank_name(pc):
    resp = await pc.post(_url(), json={"name": "  ", "template_id": "quote", "accent_hex": None})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_add_preset_rejects_bad_hex(pc):
    resp = await pc.post(_url(), json={"name": "X", "template_id": "quote", "accent_hex": "garbage"})
    assert resp.status_code == 422  # validated at the request boundary, not a 500


@pytest.mark.asyncio
async def test_add_preset_dedupes_name(pc):
    body = {"name": "Bold quote", "template_id": "quote", "accent_hex": None}
    assert (await pc.post(_url(), json=body)).status_code == 200
    assert (await pc.post(_url(), json=body)).status_code == 409


@pytest.mark.asyncio
async def test_add_preset_cap(test_db, tmp_path, monkeypatch):
    presets = [{"id": str(ObjectId()), "name": f"P{i}", "template_id": "quote",
                "accent_hex": None} for i in range(8)]
    ac = await _mk(test_db, tmp_path, monkeypatch, presets=presets)
    async with ac:
        resp = await ac.post(_url(), json={"name": "P9", "template_id": "quote",
                                           "accent_hex": None})
    app.dependency_overrides.clear()
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_add_preset_demo_blocked(test_db, tmp_path, monkeypatch):
    ac = await _mk(test_db, tmp_path, monkeypatch, is_demo=True)
    async with ac:
        resp = await ac.post(_url(), json={"name": "X", "template_id": "quote",
                                           "accent_hex": None})
    app.dependency_overrides.clear()
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_preset(pc):
    add = await pc.post(_url(), json={"name": "Bold", "template_id": "quote", "accent_hex": None})
    pid = add.json()["brand_profile"]["card_presets"][0]["id"]
    resp = await pc.delete(f"{_url()}/{pid}")
    assert resp.status_code == 200
    assert resp.json()["brand_profile"]["card_presets"] == []


@pytest.mark.asyncio
async def test_service_add_remove_roundtrip(test_db, monkeypatch):
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    await test_db.workspaces.delete_many({})
    await _seed(test_db)
    preset = CardPreset(id="p1", name="Bold", template_id="quote", accent_hex="#1C3A2E")
    ws = await add_workspace_card_preset(test_db, str(WS), str(OWNER), preset)
    assert ws is not None and ws.brand_profile.card_presets[0].id == "p1"
    ws2 = await remove_workspace_card_preset(test_db, str(WS), str(OWNER), "p1")
    assert ws2 is not None and ws2.brand_profile.card_presets == []
    await test_db.workspaces.delete_many({})


# --- ARCH-05: the cap/dedupe invariant lives in the service write ------------
# These call the service directly (bypassing the route pre-check) — the "no other
# caller can honor it" path the audit flagged.

def _preset(name: str) -> CardPreset:
    return CardPreset(id=str(ObjectId()), name=name, template_id="quote", accent_hex=None)


@pytest.mark.asyncio
async def test_service_enforces_cap_atomically(test_db, monkeypatch):
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    await test_db.workspaces.delete_many({})
    await _seed(test_db)
    for i in range(MAX_CARD_PRESETS):
        assert await add_workspace_card_preset(test_db, str(WS), str(OWNER), _preset(f"P{i}"))
    with pytest.raises(WorkspaceWriteConflict):
        await add_workspace_card_preset(test_db, str(WS), str(OWNER), _preset("over"))
    doc = await test_db.workspaces.find_one({"_id": WS})
    assert len(doc["brand_profile"]["card_presets"]) == MAX_CARD_PRESETS
    await test_db.workspaces.delete_many({})


@pytest.mark.asyncio
async def test_service_dedupes_name_atomically(test_db, monkeypatch):
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    await test_db.workspaces.delete_many({})
    await _seed(test_db)
    assert await add_workspace_card_preset(test_db, str(WS), str(OWNER), _preset("dup"))
    with pytest.raises(WorkspaceWriteConflict):
        await add_workspace_card_preset(test_db, str(WS), str(OWNER), _preset("dup"))
    doc = await test_db.workspaces.find_one({"_id": WS})
    assert len(doc["brand_profile"]["card_presets"]) == 1
    await test_db.workspaces.delete_many({})


@pytest.mark.asyncio
async def test_concurrent_adds_cannot_exceed_cap(test_db, monkeypatch):
    """Fire cap+5 distinct adds at once; the atomic $push guard lets exactly the
    cap through and rejects the rest — the TOCTOU is closed (ARCH-05)."""
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    await test_db.workspaces.delete_many({})
    await _seed(test_db)
    presets = [_preset(f"C{i}") for i in range(MAX_CARD_PRESETS + 5)]
    results = await asyncio.gather(
        *(add_workspace_card_preset(test_db, str(WS), str(OWNER), p) for p in presets),
        return_exceptions=True,
    )
    succeeded = [r for r in results if not isinstance(r, Exception)]
    rejected = [r for r in results if isinstance(r, WorkspaceWriteConflict)]
    assert len(succeeded) == MAX_CARD_PRESETS
    assert len(rejected) == 5
    doc = await test_db.workspaces.find_one({"_id": WS})
    assert len(doc["brand_profile"]["card_presets"]) == MAX_CARD_PRESETS
    await test_db.workspaces.delete_many({})
