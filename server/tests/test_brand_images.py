"""Brand-image library: upload / list / delete reusable card images on
`brand_profile.brand_images`. No vision step (unlike exemplars) — just store."""
import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
from app.main import app
from app.models.common import BrandImage, BrandProfile, utcnow
from app.models.user import UserInDB
from app.services.storage_service import get_storage
from app.services.workspace_service import (
    MAX_BRAND_IMAGES,
    WorkspaceWriteConflict,
    add_workspace_image,
)
from app.utils.dependencies import get_current_user
from tests.conftest import TEST_DB_NAME

WS_OID = ObjectId()
OWNER_OID = ObjectId()
OTHER_OID = ObjectId()
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000a49444154789c6360000002000154a24f3f0000000049454e44ae426082"
)


def _user(is_demo: bool = False, owner=OWNER_OID) -> UserInDB:
    return UserInDB(
        id=str(owner), email="o@example.com", hashed_password="x", full_name="O", is_demo=is_demo
    )


async def _seed(test_db, brand_images=None):
    await test_db.workspaces.insert_one(
        {
            "_id": WS_OID,
            "owner_id": OWNER_OID,
            "name": "Verdure",
            "slug": "verdure",
            "brand_profile": {"colors": [], "brand_images": brand_images or []},
            "vector_namespace": str(WS_OID),
            "embedding_model": settings.embedding_model,
            "embedding_dim": settings.embedding_dim,
            "asset_count": 0,
            "ready_chunk_count": 0,
            "created_at": utcnow(),
            "updated_at": utcnow(),
        }
    )


async def _mk(test_db, tmp_path, monkeypatch, *, is_demo=False, owner=OWNER_OID, brand_images=None):
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    get_storage.cache_clear()
    await _seed(test_db, brand_images)
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[get_current_user] = lambda: _user(is_demo, owner)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def bi_client(test_db, tmp_path, monkeypatch):
    ac = await _mk(test_db, tmp_path, monkeypatch)
    async with ac:
        yield ac
    app.dependency_overrides.clear()
    get_storage.cache_clear()


def _url() -> str:
    return f"/api/workspaces/{WS_OID}/brand-images"


# --- model -----------------------------------------------------------------

def test_brand_profile_brand_images_default_empty():
    assert BrandProfile().brand_images == []


def test_brand_image_shape():
    img = BrandImage(id="abc", storage_key="ws/images/abc/c.png", url="/u", name="c.png")
    assert img.id == "abc" and img.name == "c.png"


# --- routes ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_brand_image_appends_and_stores(bi_client):
    resp = await bi_client.post(_url(), files={"file": ("photo.png", PNG, "image/png")})
    assert resp.status_code == 200
    imgs = resp.json()["brand_profile"]["brand_images"]
    assert len(imgs) == 1
    assert imgs[0]["name"] == "photo.png"
    assert imgs[0]["storage_key"].startswith(f"{WS_OID}/images/")
    assert imgs[0]["url"].startswith(f"/api/workspaces/{WS_OID}/images/file/")
    assert await get_storage().read(imgs[0]["storage_key"]) == PNG


@pytest.mark.asyncio
async def test_add_brand_image_rejects_bad_type(bi_client):
    resp = await bi_client.post(_url(), files={"file": ("c.txt", b"hi", "text/plain")})
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_add_brand_image_enforces_cap(test_db, tmp_path, monkeypatch):
    full = [
        {"id": str(ObjectId()), "storage_key": f"k{i}", "url": None, "name": "n"}
        for i in range(MAX_BRAND_IMAGES)
    ]
    ac = await _mk(test_db, tmp_path, monkeypatch, brand_images=full)
    async with ac:
        resp = await ac.post(_url(), files={"file": ("photo.png", PNG, "image/png")})
    app.dependency_overrides.clear()
    get_storage.cache_clear()
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_add_brand_image_demo_blocked(test_db, tmp_path, monkeypatch):
    ac = await _mk(test_db, tmp_path, monkeypatch, is_demo=True)
    async with ac:
        resp = await ac.post(_url(), files={"file": ("photo.png", PNG, "image/png")})
    app.dependency_overrides.clear()
    get_storage.cache_clear()
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_add_brand_image_cross_owner_404(test_db, tmp_path, monkeypatch):
    ac = await _mk(test_db, tmp_path, monkeypatch, owner=OTHER_OID)
    async with ac:
        resp = await ac.post(_url(), files={"file": ("photo.png", PNG, "image/png")})
    app.dependency_overrides.clear()
    get_storage.cache_clear()
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_brand_patch_preserves_library_and_exemplars(test_db, tmp_path, monkeypatch):
    """A brand-identity Save (whole-profile PATCH) must not wipe ANY of the five
    sub-collections that have their own endpoints — the image library, exemplars,
    uploaded fonts, and card presets. (The whole point of the preservation guard;
    the client omits all of these on every identity Save — see BUILD-01.)"""
    imgs = [{"id": "i1", "storage_key": "k1", "url": "/u", "name": "a.png"}]
    exs = [{"id": "e1", "storage_key": "ke", "url": "/u", "style_note": "Punchy."}]
    fonts = [{"id": "f1", "family": "Acme Sans", "storage_key": "kf", "url": "/u"}]
    presets = [{"id": "p1", "name": "Bold quote", "template_id": "quote", "accent_hex": "#1C3A2E"}]
    ac = await _mk(test_db, tmp_path, monkeypatch, brand_images=imgs)
    await test_db.workspaces.update_one(
        {"_id": WS_OID},
        {
            "$set": {
                "brand_profile.exemplars": exs,
                "brand_profile.uploaded_fonts": fonts,
                "brand_profile.card_presets": presets,
            }
        },
    )
    async with ac:
        resp = await ac.patch(
            f"/api/workspaces/{WS_OID}",
            json={
                "brand_profile": {
                    "colors": [{"name": "Green", "hex": "#1C3A2E", "role": "primary"}],
                    "accent_hex": None,
                    "fonts": {"heading": None, "body": None, "mono": None},
                    "logo": None,
                    "voice_summary": "New voice.",
                }
            },
        )
    app.dependency_overrides.clear()
    get_storage.cache_clear()
    assert resp.status_code == 200
    bp = resp.json()["brand_profile"]
    assert bp["voice_summary"] == "New voice."  # the edit applied
    assert [i["id"] for i in bp["brand_images"]] == ["i1"]  # library preserved
    assert [e["id"] for e in bp["exemplars"]] == ["e1"]  # exemplars preserved
    assert [f["id"] for f in bp["uploaded_fonts"]] == ["f1"]  # fonts preserved
    assert [p["id"] for p in bp["card_presets"]] == ["p1"]  # presets preserved


@pytest.mark.asyncio
async def test_delete_brand_image_pulls_and_removes_bytes(bi_client):
    add = await bi_client.post(_url(), files={"file": ("photo.png", PNG, "image/png")})
    img = add.json()["brand_profile"]["brand_images"][0]
    resp = await bi_client.delete(f"{_url()}/{img['id']}")
    assert resp.status_code == 200
    assert resp.json()["brand_profile"]["brand_images"] == []
    with pytest.raises(FileNotFoundError):
        await get_storage().read(img["storage_key"])


_ONE_IMAGE = {"id": "img1", "storage_key": "k1", "url": "/u", "name": "old.png"}


@pytest.mark.asyncio
async def test_rename_brand_image_updates_name(test_db, tmp_path, monkeypatch):
    ac = await _mk(test_db, tmp_path, monkeypatch, brand_images=[dict(_ONE_IMAGE)])
    async with ac:
        resp = await ac.patch(f"{_url()}/img1", json={"name": "Forest texture"})
    app.dependency_overrides.clear()
    get_storage.cache_clear()
    assert resp.status_code == 200
    assert [i["name"] for i in resp.json()["brand_profile"]["brand_images"]] == ["Forest texture"]


@pytest.mark.asyncio
async def test_rename_brand_image_blank_keeps_existing(test_db, tmp_path, monkeypatch):
    ac = await _mk(test_db, tmp_path, monkeypatch, brand_images=[dict(_ONE_IMAGE)])
    async with ac:
        resp = await ac.patch(f"{_url()}/img1", json={"name": "   "})
    app.dependency_overrides.clear()
    get_storage.cache_clear()
    assert resp.json()["brand_profile"]["brand_images"][0]["name"] == "old.png"


@pytest.mark.asyncio
async def test_rename_brand_image_clamps_length(test_db, tmp_path, monkeypatch):
    ac = await _mk(test_db, tmp_path, monkeypatch, brand_images=[dict(_ONE_IMAGE)])
    async with ac:
        resp = await ac.patch(f"{_url()}/img1", json={"name": "x" * 200})
    app.dependency_overrides.clear()
    get_storage.cache_clear()
    assert len(resp.json()["brand_profile"]["brand_images"][0]["name"]) == 80


@pytest.mark.asyncio
async def test_rename_brand_image_demo_blocked(test_db, tmp_path, monkeypatch):
    ac = await _mk(test_db, tmp_path, monkeypatch, is_demo=True, brand_images=[dict(_ONE_IMAGE)])
    async with ac:
        resp = await ac.patch(f"{_url()}/img1", json={"name": "X"})
    app.dependency_overrides.clear()
    get_storage.cache_clear()
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_service_enforces_cap_atomically(test_db, monkeypatch):
    """The cap is enforced by the service write, not just the route pre-check —
    a direct caller can't exceed it (ARCH-05)."""
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    await _seed(test_db)
    for i in range(MAX_BRAND_IMAGES):
        img = BrandImage(id=str(ObjectId()), storage_key=f"k{i}", url=None, name="n")
        assert await add_workspace_image(test_db, str(WS_OID), str(OWNER_OID), img)
    over = BrandImage(id=str(ObjectId()), storage_key="over", url=None, name="n")
    with pytest.raises(WorkspaceWriteConflict):
        await add_workspace_image(test_db, str(WS_OID), str(OWNER_OID), over)
    doc = await test_db.workspaces.find_one({"_id": WS_OID})
    assert len(doc["brand_profile"]["brand_images"]) == MAX_BRAND_IMAGES
