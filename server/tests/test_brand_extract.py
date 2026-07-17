"""Brand auto-extraction (Phase 4c). The Pillow palette step is deterministic and
unit-tested directly; the route is tested with the vision service faked (no model
call), asserting it returns a proposal, validates the upload, allows the demo
user, and **never mutates** the workspace."""
import io

import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.config import settings
from app.database import get_database
from app.main import app
from app.models.common import BrandColor, BrandFonts, utcnow
from app.models.user import UserInDB
from app.models.workspace import BrandExtractResponse
from app.services.brand_extract_service import (
    BrandExtractService,
    build_extract_response,
    extract_palette,
)
from app.utils.dependencies import get_current_user
from tests.conftest import TEST_DB_NAME

WORKSPACE_OID = ObjectId()
OWNER_OID = ObjectId()


def _png(color: tuple[int, int, int], size: tuple[int, int] = (16, 16)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


# --- Pillow palette (pure, no network) -------------------------------------

def test_extract_palette_reads_dominant_color_first():
    img = Image.new("RGB", (10, 10), (255, 0, 0))  # 60 red px
    img.paste(Image.new("RGB", (4, 10), (0, 0, 255)), (0, 0))  # 40 blue px
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    hexes = extract_palette(buf.getvalue())
    assert hexes[0] == "#FF0000"
    assert "#0000FF" in hexes
    assert len(hexes) == len(set(hexes))  # de-duped


def test_extract_palette_single_color():
    assert extract_palette(_png((28, 58, 46))) == ["#1C3A2E"]


# --- build_extract_response (shaping) --------------------------------------

def test_build_extract_response_normalizes_and_falls_back():
    out = build_extract_response(
        ["#1C3A2E"],
        {
            "colors": [{"name": "Forest", "hex": "#1C3A2E", "role": "primary"}],
            "voice_summary": "  ",  # blank -> None
            "fonts": {"heading": "Fraunces", "body": "", "mono": "  "},
        },
    )
    assert out.colors == [BrandColor(name="Forest", hex="#1C3A2E", role="primary")]
    assert out.voice_summary is None
    assert out.fonts == BrandFonts(heading="Fraunces", body=None, mono=None)


def test_build_extract_response_falls_back_to_detected_palette():
    out = build_extract_response(["#112233"], {"colors": [], "voice_summary": "v", "fonts": {}})
    assert out.colors == [BrandColor(name="#112233", hex="#112233", role="primary")]
    assert out.voice_summary == "v"


# --- Route (vision service faked) ------------------------------------------

class _FakeExtractService:
    async def propose(self, data: bytes, media_type: str) -> BrandExtractResponse:
        return BrandExtractResponse(
            colors=[BrandColor(name="Forest", hex="#1C3A2E", role="primary")],
            voice_summary="Calm, precise.",
            fonts=BrandFonts(heading="Fraunces", body="Inter", mono=None),
        )


def _owner_user(is_demo: bool = False) -> UserInDB:
    return UserInDB(
        id=str(OWNER_OID), email="owner@example.com", hashed_password="x",
        full_name="Owner", is_demo=is_demo,
    )


async def _seed_workspace(test_db) -> None:
    now = utcnow()
    await test_db.workspaces.insert_one(
        {
            "_id": WORKSPACE_OID,
            "owner_id": OWNER_OID,
            "name": "Verdure",
            "slug": "verdure",
            "brand_profile": {"colors": [{"name": "Old", "hex": "#000000", "role": "primary"}]},
            "vector_namespace": str(WORKSPACE_OID),
            "embedding_model": settings.embedding_model,
            "embedding_dim": settings.embedding_dim,
            "asset_count": 0,
            "ready_chunk_count": 0,
            "created_at": now,
            "updated_at": now,
        }
    )


def _url() -> str:
    return f"/api/workspaces/{WORKSPACE_OID}/brand/extract"


async def _make_client(test_db, monkeypatch, *, is_demo: bool) -> AsyncClient:
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    await _seed_workspace(test_db)
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[get_current_user] = lambda: _owner_user(is_demo)
    app.dependency_overrides[BrandExtractService] = lambda: _FakeExtractService()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def client(test_db, monkeypatch):
    ac = await _make_client(test_db, monkeypatch, is_demo=False)
    async with ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def demo_client(test_db, monkeypatch):
    ac = await _make_client(test_db, monkeypatch, is_demo=True)
    async with ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_extract_returns_proposal_without_mutating(client, test_db):
    resp = await client.post(_url(), files={"file": ("logo.png", _png((28, 58, 46)), "image/png")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["colors"][0]["hex"] == "#1C3A2E"
    assert body["voice_summary"] == "Calm, precise."
    assert body["fonts"]["heading"] == "Fraunces"
    # Nothing persisted — the workspace's stored brand_profile is untouched.
    doc = await test_db.workspaces.find_one({"_id": WORKSPACE_OID})
    assert doc["brand_profile"]["colors"] == [{"name": "Old", "hex": "#000000", "role": "primary"}]


@pytest.mark.asyncio
async def test_extract_rejects_bad_type(client):
    resp = await client.post(_url(), files={"file": ("notes.txt", b"hi", "text/plain")})
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_extract_rejects_empty(client):
    resp = await client.post(_url(), files={"file": ("logo.png", b"", "image/png")})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_extract_rejects_oversize(client, monkeypatch):
    monkeypatch.setattr("app.routes.workspaces.MAX_IMAGE_BYTES", 4)
    resp = await client.post(_url(), files={"file": ("logo.png", _png((1, 2, 3)), "image/png")})
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_extract_allowed_for_demo(demo_client):
    # Extraction is generative (a proposal), not a mutation — demo is allowed.
    resp = await demo_client.post(_url(), files={"file": ("logo.png", _png((28, 58, 46)), "image/png")})
    assert resp.status_code == 200
