"""Uploaded brand fonts: model + service + routes / PDF embedding."""
from dataclasses import replace

import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
from app.main import app
from app.models.common import BrandProfile, UploadedFont, utcnow
from app.models.user import UserInDB
from app.services.storage_service import build_font_key, get_storage
from app.services.upload_service import FONT_POLICY
from app.services.workspace_service import resolve_uploaded_font
from app.utils.dependencies import get_current_user
from tests.conftest import TEST_DB_NAME


def test_uploaded_font_default_empty():
    assert BrandProfile().uploaded_fonts == []


def test_uploaded_font_shape():
    f = UploadedFont(id="f1", family="Acme Sans", storage_key="k", url="/u")
    assert f.family == "Acme Sans"


def test_build_font_key_is_server_derived():
    assert build_font_key("ws1", "f1", "Acme Sans.ttf") == "ws1/fonts/f1/Acme_Sans.ttf"


def test_resolve_uploaded_font_matches_family():
    bp = {"uploaded_fonts": [{"id": "f1", "family": "Acme Sans", "storage_key": "k1", "url": "/u"}]}
    assert resolve_uploaded_font(bp, "Acme Sans") == "k1"
    assert resolve_uploaded_font(bp, "Inter") is None
    assert resolve_uploaded_font({}, "Acme Sans") is None


WS = ObjectId()
OWNER = ObjectId()
TTF_HEX = "0001000000010000"  # sfnt version 1.0 header (enough for the route's checks)


def _user(is_demo=False, owner=OWNER):
    return UserInDB(id=str(owner), email="o@e.com", hashed_password="x", full_name="O",
                    is_demo=is_demo)


async def _seed(db, fonts=None):
    await db.workspaces.insert_one({
        "_id": WS, "owner_id": OWNER, "name": "V", "slug": "v",
        "brand_profile": {"uploaded_fonts": fonts or []}, "vector_namespace": str(WS),
        "embedding_model": settings.embedding_model, "embedding_dim": settings.embedding_dim,
        "asset_count": 0, "ready_chunk_count": 0, "created_at": utcnow(), "updated_at": utcnow(),
    })


async def _mk(test_db, tmp_path, monkeypatch, *, is_demo=False, owner=OWNER, fonts=None):
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    get_storage.cache_clear()
    await _seed(test_db, fonts)
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[get_current_user] = lambda: _user(is_demo, owner)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _url():
    return f"/api/workspaces/{WS}/fonts"


@pytest_asyncio.fixture
async def fc(test_db, tmp_path, monkeypatch):
    ac = await _mk(test_db, tmp_path, monkeypatch)
    async with ac:
        yield ac
    app.dependency_overrides.clear()
    get_storage.cache_clear()


@pytest.mark.asyncio
async def test_add_font_stores_and_appends(fc):
    resp = await fc.post(_url(), data={"name": "Acme Sans"},
                         files={"file": ("acme.ttf", bytes.fromhex(TTF_HEX), "font/ttf")})
    assert resp.status_code == 200
    fonts = resp.json()["brand_profile"]["uploaded_fonts"]
    assert fonts[0]["family"] == "Acme Sans"
    assert fonts[0]["storage_key"].startswith(f"{WS}/fonts/")
    assert await get_storage().read(fonts[0]["storage_key"]) == bytes.fromhex(TTF_HEX)


@pytest.mark.asyncio
async def test_add_font_rejects_non_ttf(fc):
    resp = await fc.post(_url(), data={"name": "X"},
                         files={"file": ("x.otf", b"hi", "font/otf")})
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_add_font_rejects_empty(fc):
    # The consolidated read_upload gate (ARCH-01) still 400s an empty upload.
    resp = await fc.post(_url(), data={"name": "Empty"}, files={"file": ("x.ttf", b"", "font/ttf")})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_add_font_rejects_oversize(fc, monkeypatch):
    # Shrinking FONT_POLICY exercises the 413 path + the "Font" noun via the gate.
    monkeypatch.setattr("app.routes.workspaces.FONT_POLICY", replace(FONT_POLICY, max_bytes=4))
    resp = await fc.post(
        _url(), data={"name": "Big"}, files={"file": ("x.ttf", bytes.fromhex(TTF_HEX), "font/ttf")}
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_add_font_rejects_css_injection_name(fc):
    """The family is a user label interpolated near CSS on the client; a name with
    CSS-breaking characters is rejected at the boundary (SEC-11)."""
    evil = 'X";}body{background:url(//evil)}@font-face{font-family:"Y'
    resp = await fc.post(_url(), data={"name": evil},
                         files={"file": ("ok.ttf", bytes.fromhex(TTF_HEX), "font/ttf")})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_add_font_demo_blocked(test_db, tmp_path, monkeypatch):
    ac = await _mk(test_db, tmp_path, monkeypatch, is_demo=True)
    async with ac:
        resp = await ac.post(_url(), data={"name": "X"},
                             files={"file": ("x.ttf", bytes.fromhex(TTF_HEX), "font/ttf")})
    app.dependency_overrides.clear()
    get_storage.cache_clear()
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_and_serve_font(fc):
    add = await fc.post(_url(), data={"name": "Acme"},
                        files={"file": ("acme.ttf", bytes.fromhex(TTF_HEX), "font/ttf")})
    font = add.json()["brand_profile"]["uploaded_fonts"][0]
    fid = font["id"]
    served = await fc.get(font["url"])
    assert served.status_code == 200
    assert served.content == bytes.fromhex(TTF_HEX)
    resp = await fc.delete(f"{_url()}/{fid}")
    assert resp.status_code == 200
    assert resp.json()["brand_profile"]["uploaded_fonts"] == []


def test_register_pdf_font_uses_uploaded_bytes():
    from pathlib import Path

    from app.services import document_service as ds

    ttf = (Path(ds.__file__).resolve().parents[1] / "assets" / "fonts" / "inter.ttf").read_bytes()
    ds._REGISTERED.clear()
    name = ds._register_pdf_font("Acme Sans", "body", {"Acme Sans": ttf})
    assert name == "bcs-body-acme-sans"  # embedded, not a base-14 fallback
