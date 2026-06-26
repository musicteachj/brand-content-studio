"""Exemplar steering (Phase 4c PR-C): the prompt-guidance builder is pure; the
extraction + routes are tested with the vision service faked (no model call)."""
import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
from app.main import app
from app.models.common import BrandExemplar, BrandProfile, utcnow
from app.models.user import UserInDB
from app.prompts import image_card, text_post
from app.prompts.brand_extract import (
    EXEMPLAR_NOTE_TOOL,
    build_exemplar_system,
    build_exemplar_user,
)
from app.prompts.exemplars import build_exemplar_guidance
from app.services.brand_extract_service import BrandExtractService
from app.services.storage_service import get_storage
from app.utils.dependencies import get_current_user
from tests.conftest import TEST_DB_NAME


# --- build_exemplar_guidance (pure) ----------------------------------------

def test_build_exemplar_guidance_joins_notes():
    out = build_exemplar_guidance(
        ["Punchy hook, short body.", "Earthy photography, lots of negative space."]
    )
    assert out is not None
    assert "1. Punchy hook, short body." in out
    assert "2. Earthy photography, lots of negative space." in out
    assert "do not copy their exact words" in out.lower()


def test_build_exemplar_guidance_empty_returns_none():
    assert build_exemplar_guidance([]) is None
    assert build_exemplar_guidance(["", "   "]) is None


# --- system-prompt threading -----------------------------------------------

def test_text_post_system_appends_exemplar_block():
    g = "On-brand examples to emulate (the brand's own past cards...):\n1. Punchy."
    assert "Punchy." in text_post.build_system("Grounded voice.", g)
    assert "Punchy." not in text_post.build_system("Grounded voice.")


def test_card_copy_system_appends_exemplar_block():
    g = "examples...\n1. Earthy."
    assert "Earthy." in image_card.build_copy_system("V", g)
    assert "Earthy." not in image_card.build_copy_system("V")


# --- model -----------------------------------------------------------------

def test_brand_profile_exemplars_default_empty():
    assert BrandProfile().exemplars == []


def test_brand_exemplar_shape():
    e = BrandExemplar(id="abc", storage_key="ws/images/abc/c.png", url="/u", style_note="Punchy.")
    assert e.id == "abc" and e.style_note == "Punchy."


# --- extraction prompt/tool ------------------------------------------------

def test_exemplar_note_tool_schema():
    assert EXEMPLAR_NOTE_TOOL["name"] == "exemplar_note"
    assert EXEMPLAR_NOTE_TOOL["strict"] is True
    assert EXEMPLAR_NOTE_TOOL["input_schema"]["required"] == ["style_note"]


def test_exemplar_prompt_builders_nonempty():
    assert "do not" in build_exemplar_system().lower()
    assert build_exemplar_user().strip()


# --- routes (vision service faked) -----------------------------------------

WS_OID = ObjectId()
OWNER_OID = ObjectId()
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000a49444154789c6360000002000154a24f3f0000000049454e44ae426082"
)


class _FakeExtract:
    async def propose_exemplar_note(self, data: bytes, media_type: str) -> str:
        return "Punchy hook, one tight line, earthy photography."


def _user(is_demo: bool = False) -> UserInDB:
    return UserInDB(
        id=str(OWNER_OID), email="o@example.com", hashed_password="x", full_name="O", is_demo=is_demo
    )


async def _seed(test_db, exemplars=None):
    await test_db.workspaces.insert_one(
        {
            "_id": WS_OID,
            "owner_id": OWNER_OID,
            "name": "Verdure",
            "slug": "verdure",
            "brand_profile": {"colors": [], "exemplars": exemplars or []},
            "vector_namespace": str(WS_OID),
            "embedding_model": settings.embedding_model,
            "embedding_dim": settings.embedding_dim,
            "asset_count": 0,
            "ready_chunk_count": 0,
            "created_at": utcnow(),
            "updated_at": utcnow(),
        }
    )


async def _mk(test_db, tmp_path, monkeypatch, *, is_demo=False, exemplars=None):
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    get_storage.cache_clear()
    await _seed(test_db, exemplars)
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[get_current_user] = lambda: _user(is_demo)
    app.dependency_overrides[BrandExtractService] = lambda: _FakeExtract()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def ex_client(test_db, tmp_path, monkeypatch):
    ac = await _mk(test_db, tmp_path, monkeypatch)
    async with ac:
        yield ac
    app.dependency_overrides.clear()
    get_storage.cache_clear()


def _url() -> str:
    return f"/api/workspaces/{WS_OID}/exemplars"


@pytest.mark.asyncio
async def test_add_exemplar_appends_and_stores(ex_client, test_db):
    resp = await ex_client.post(_url(), files={"file": ("card.png", PNG, "image/png")})
    assert resp.status_code == 200
    exemplars = resp.json()["brand_profile"]["exemplars"]
    assert len(exemplars) == 1
    assert exemplars[0]["style_note"].startswith("Punchy hook")
    assert exemplars[0]["storage_key"].startswith(f"{WS_OID}/images/")
    assert await get_storage().read(exemplars[0]["storage_key"]) == PNG


@pytest.mark.asyncio
async def test_add_exemplar_rejects_bad_type(ex_client):
    resp = await ex_client.post(_url(), files={"file": ("c.txt", b"hi", "text/plain")})
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_add_exemplar_enforces_cap(test_db, tmp_path, monkeypatch):
    full = [
        {"id": str(ObjectId()), "storage_key": f"k{i}", "url": None, "style_note": "n"}
        for i in range(5)
    ]
    ac = await _mk(test_db, tmp_path, monkeypatch, exemplars=full)
    async with ac:
        resp = await ac.post(_url(), files={"file": ("card.png", PNG, "image/png")})
    app.dependency_overrides.clear()
    get_storage.cache_clear()
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_add_exemplar_demo_blocked(test_db, tmp_path, monkeypatch):
    ac = await _mk(test_db, tmp_path, monkeypatch, is_demo=True)
    async with ac:
        resp = await ac.post(_url(), files={"file": ("card.png", PNG, "image/png")})
    app.dependency_overrides.clear()
    get_storage.cache_clear()
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_exemplar_pulls_and_removes_bytes(ex_client, test_db):
    add = await ex_client.post(_url(), files={"file": ("card.png", PNG, "image/png")})
    ex = add.json()["brand_profile"]["exemplars"][0]
    resp = await ex_client.delete(f"{_url()}/{ex['id']}")
    assert resp.status_code == 200
    assert resp.json()["brand_profile"]["exemplars"] == []
    with pytest.raises(FileNotFoundError):
        await get_storage().read(ex["storage_key"])
