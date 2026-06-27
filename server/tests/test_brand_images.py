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
from app.services.workspace_service import MAX_BRAND_IMAGES
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
async def test_delete_brand_image_pulls_and_removes_bytes(bi_client):
    add = await bi_client.post(_url(), files={"file": ("photo.png", PNG, "image/png")})
    img = add.json()["brand_profile"]["brand_images"][0]
    resp = await bi_client.delete(f"{_url()}/{img['id']}")
    assert resp.status_code == 200
    assert resp.json()["brand_profile"]["brand_images"] == []
    with pytest.raises(FileNotFoundError):
        await get_storage().read(img["storage_key"])
