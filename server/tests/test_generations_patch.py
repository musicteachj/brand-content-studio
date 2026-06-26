"""Integration: PATCH /generations/{id} — Phase 1.5 client-side customization.
Inline field edits, layout (template) swap, and the per-card accent all merge
into `output` with NO model call. Card-only guard + accent palette guard hold."""
import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
from app.main import app
from app.models.common import utcnow
from app.utils.dependencies import get_workspace_or_404
from tests.conftest import TEST_DB_NAME

WORKSPACE_OID = ObjectId()
OWNER_OID = ObjectId()

# The Verdure palette the accent guard validates against.
PALETTE = [
    {"name": "Forest", "hex": "#1C3A2E", "role": "primary"},
    {"name": "Cream", "hex": "#F4F1E9", "role": "neutral"},
    {"name": "Clay", "hex": "#C98A3D", "role": "accent"},
]


def _workspace() -> dict:
    return {
        "_id": WORKSPACE_OID,
        "owner_id": OWNER_OID,
        "brand_profile": {"colors": PALETTE},
    }


@pytest_asyncio.fixture
async def client(test_db, monkeypatch):
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[get_workspace_or_404] = lambda: _workspace()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _seed_card(test_db, *, type_: str = "card") -> str:
    now = utcnow()
    doc = {
        "_id": ObjectId(),
        "workspace_id": WORKSPACE_OID,
        "owner_id": OWNER_OID,
        "type": type_,
        "brief": "Hempcrete embodied carbon",
        "status": "complete",
        "output": {
            "template_id": "photo-led",
            "fields": {
                "eyebrow": "MATERIALS",
                "headline": "The carbon math is changing",
                "body": "Hempcrete sequesters carbon as it cures.",
                "cta": "Read the brief",
                "hashtag": "#Hempcrete",
            },
            "image": None,
            "suggested_keywords": ["hemp", "construction"],
            "accent_hex": None,
        }
        if type_ == "card"
        else {"post_text": "A text post.", "hashtags": [], "char_count": 11},
        "retrieved_chunk_ids": ["posts-asset:0"],
        "retrieval_meta": [],
        "model": settings.ai_model,
        "embedding_query_model": settings.embedding_model,
        "created_at": now,
        "updated_at": now,
    }
    await test_db.generations.insert_one(doc)
    return str(doc["_id"])


def _url(gid: str) -> str:
    return f"/api/workspaces/{WORKSPACE_OID}/generations/{gid}"


@pytest.mark.asyncio
async def test_patch_updates_fields_inline_edit(client, test_db):
    gid = await _seed_card(test_db)
    resp = await client.patch(
        _url(gid),
        json={"fields": {"eyebrow": "MATERIALS", "headline": "A sharper headline",
                          "body": "Edited body.", "cta": "Read on", "hashtag": "#Verdure"}},
    )
    assert resp.status_code == 200
    out = resp.json()["output"]
    assert out["fields"]["headline"] == "A sharper headline"
    # The rest of the output is preserved (partial merge, not a wipe).
    assert out["template_id"] == "photo-led"
    assert out["suggested_keywords"] == ["hemp", "construction"]

    doc = await test_db.generations.find_one({"_id": ObjectId(gid)})
    assert doc["output"]["fields"]["body"] == "Edited body."


@pytest.mark.asyncio
async def test_patch_swaps_template_keeps_copy(client, test_db):
    gid = await _seed_card(test_db)
    resp = await client.patch(_url(gid), json={"template_id": "quote"})
    assert resp.status_code == 200
    out = resp.json()["output"]
    assert out["template_id"] == "quote"
    # Layout swap must not touch the copy.
    assert out["fields"]["headline"] == "The carbon math is changing"


@pytest.mark.asyncio
async def test_patch_accent_accepts_palette_color(client, test_db):
    gid = await _seed_card(test_db)
    resp = await client.patch(_url(gid), json={"accent_hex": "#C98A3D"})
    assert resp.status_code == 200
    assert resp.json()["output"]["accent_hex"] == "#C98A3D"


@pytest.mark.asyncio
async def test_patch_accent_rejects_non_palette_color(client, test_db):
    gid = await _seed_card(test_db)
    resp = await client.patch(_url(gid), json={"accent_hex": "#FF00FF"})
    assert resp.status_code == 422
    # Output unchanged.
    doc = await test_db.generations.find_one({"_id": ObjectId(gid)})
    assert doc["output"]["accent_hex"] is None


@pytest.mark.asyncio
async def test_patch_accent_rejects_malformed_hex(client, test_db):
    gid = await _seed_card(test_db)
    resp = await client.patch(_url(gid), json={"accent_hex": "not-a-color"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_rejects_text_generation(client, test_db):
    gid = await _seed_card(test_db, type_="text")
    resp = await client.patch(_url(gid), json={"template_id": "quote"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_patch_empty_payload_is_rejected(client, test_db):
    gid = await _seed_card(test_db)
    resp = await client.patch(_url(gid), json={})
    assert resp.status_code == 400
