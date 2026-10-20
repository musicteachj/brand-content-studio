"""Integration: PATCH /generations/{id} — Phase 1.5 client-side customization.
Inline field edits, layout (template) swap, and the per-card accent all merge
into `output` with NO model call. Card-only guard + accent palette guard hold."""
import asyncio

import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
from app.main import app
from app.models.common import utcnow
from app.services import generations_service
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


async def _seed_post_pack(test_db) -> str:
    """A post_pack persists the caption at the top of `output` with the card
    nested under `output.card` (Phase 3)."""
    now = utcnow()
    doc = {
        "_id": ObjectId(),
        "workspace_id": WORKSPACE_OID,
        "owner_id": OWNER_OID,
        "type": "post_pack",
        "brief": "Hempcrete embodied carbon",
        "status": "complete",
        "output": {
            "post_text": "Specify hempcrete early.\n\n#Hempcrete",
            "hashtags": ["#Hempcrete"],
            "char_count": 32,
            "card": {
                "template_id": "photo-led",
                "fields": {"eyebrow": "MATERIALS", "headline": "Carbon, in the wall",
                           "body": "", "cta": "Read on", "hashtag": "#Hempcrete"},
                "image": None,
                "suggested_keywords": ["hemp"],
                "accent_hex": None,
            },
        },
        "retrieved_chunk_ids": ["posts-asset:0"],
        "retrieval_meta": [],
        "model": settings.ai_model,
        "embedding_query_model": settings.embedding_model,
        "created_at": now,
        "updated_at": now,
    }
    await test_db.generations.insert_one(doc)
    return str(doc["_id"])


@pytest.mark.asyncio
async def test_patch_post_pack_attaches_image_into_nested_card(client, test_db):
    gid = await _seed_post_pack(test_db)
    resp = await client.patch(
        _url(gid),
        json={"image": {"source": "unsplash", "url": "http://x/i.jpg", "unsplash_id": "abc",
                        "attribution": {"author": "Jo", "author_url": "http://x", "source_url": "http://x"}}},
    )
    assert resp.status_code == 200
    out = resp.json()["output"]
    # Image merges into output.card, not the top level; caption + card copy preserved.
    assert out["card"]["image"]["unsplash_id"] == "abc"
    assert "image" not in out or out.get("image") is None
    assert out["post_text"].startswith("Specify hempcrete")
    assert out["card"]["fields"]["headline"] == "Carbon, in the wall"


@pytest.mark.asyncio
async def test_patch_post_pack_accent_validates_against_palette(client, test_db):
    gid = await _seed_post_pack(test_db)
    ok = await client.patch(_url(gid), json={"accent_hex": "#C98A3D"})
    assert ok.status_code == 200
    assert ok.json()["output"]["card"]["accent_hex"] == "#C98A3D"
    bad = await client.patch(_url(gid), json={"accent_hex": "#FF00FF"})
    assert bad.status_code == 422


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


_IMAGE = {"source": "unsplash", "url": "http://x/i.jpg", "unsplash_id": "abc",
          "attribution": {"author": "Jo", "author_url": "http://x", "source_url": "http://x"}}


@pytest.mark.asyncio
async def test_patch_image_null_clears_a_card_image(client, test_db):
    """QA-07: "Remove image" sends `{"image": null}`; it must clear the saved image."""
    gid = await _seed_card(test_db)
    assert (await client.patch(_url(gid), json={"image": _IMAGE})).status_code == 200

    resp = await client.patch(_url(gid), json={"image": None})
    assert resp.status_code == 200
    assert resp.json()["output"]["image"] is None
    stored = await test_db.generations.find_one({"_id": ObjectId(gid)})
    assert stored["output"]["image"] is None
    # The rest of the card is untouched.
    assert stored["output"]["fields"]["headline"] == "The carbon math is changing"


@pytest.mark.asyncio
async def test_patch_image_null_clears_a_post_pack_card_image(client, test_db):
    gid = await _seed_post_pack(test_db)
    assert (await client.patch(_url(gid), json={"image": _IMAGE})).status_code == 200

    resp = await client.patch(_url(gid), json={"image": None})
    assert resp.status_code == 200
    out = resp.json()["output"]
    assert out["card"]["image"] is None
    assert out["card"]["fields"]["headline"] == "Carbon, in the wall"


@pytest.mark.asyncio
async def test_patch_null_for_other_fields_is_still_ignored(client, test_db):
    """Only `image` can be cleared: a null template, fields, or accent never wipes them."""
    gid = await _seed_card(test_db)
    resp = await client.patch(_url(gid), json={"template_id": None, "fields": None, "accent_hex": None})
    assert resp.status_code == 400
    stored = await test_db.generations.find_one({"_id": ObjectId(gid)})
    assert stored["output"]["template_id"] == "photo-led"



@pytest.mark.asyncio
@pytest.mark.parametrize("seed", ["card", "post_pack"])
async def test_concurrent_patches_dont_overwrite_each_other(client, test_db, seed):
    """Removing the image while a text edit saves must keep both changes: each update
    writes only its own fields, never the whole `output` it read earlier."""
    gid = await (_seed_card(test_db) if seed == "card" else _seed_post_pack(test_db))
    assert (await client.patch(_url(gid), json={"image": _IMAGE})).status_code == 200
    fields = {"eyebrow": "E", "headline": "Edited headline", "body": "", "cta": "C", "hashtag": "#H"}
    nested_key = None if seed == "card" else "card"

    await asyncio.gather(
        generations_service.update_generation_output(
            test_db, WORKSPACE_OID, gid, {"image": None}, nested_key=nested_key
        ),
        generations_service.update_generation_output(
            test_db, WORKSPACE_OID, gid, {"fields": fields}, nested_key=nested_key
        ),
    )
    stored = (await test_db.generations.find_one({"_id": ObjectId(gid)}))["output"]
    card = stored if seed == "card" else stored["card"]
    assert card["image"] is None
    assert card["fields"]["headline"] == "Edited headline"


@pytest.mark.asyncio
async def test_partial_fields_patch_still_stores_the_full_card_copy(client, test_db):
    """Nested models keep their defaults: a `fields` patch stores all five keys."""
    gid = await _seed_card(test_db)
    resp = await client.patch(_url(gid), json={"fields": {"headline": "Only this"}})
    assert resp.status_code == 200
    stored = (await test_db.generations.find_one({"_id": ObjectId(gid)}))["output"]["fields"]
    assert stored == {"eyebrow": "", "headline": "Only this", "body": "", "cta": "", "hashtag": ""}


@pytest.mark.asyncio
async def test_post_pack_without_a_card_object_gets_one(client, test_db):
    gid = await _seed_post_pack(test_db)
    await test_db.generations.update_one({"_id": ObjectId(gid)}, {"$set": {"output.card": None}})
    resp = await client.patch(_url(gid), json={"image": _IMAGE})
    assert resp.status_code == 200
    assert resp.json()["output"]["card"]["image"]["unsplash_id"] == "abc"
    assert resp.json()["output"]["post_text"].startswith("Specify hempcrete")


@pytest.mark.asyncio
async def test_card_with_a_null_output_still_patches(client, test_db):
    gid = await _seed_card(test_db)
    await test_db.generations.update_one({"_id": ObjectId(gid)}, {"$set": {"output": None}})
    resp = await client.patch(_url(gid), json={"image": _IMAGE})
    assert resp.status_code == 200
    assert resp.json()["output"]["image"]["unsplash_id"] == "abc"


@pytest.mark.asyncio
async def test_patch_unknown_generation_is_404(client, test_db):
    resp = await client.patch(_url(str(ObjectId())), json={"image": None})
    assert resp.status_code == 404
