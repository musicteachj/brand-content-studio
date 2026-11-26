"""The asset delete route uses the normalized id for the vectors and the files."""
import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

import app.routes.assets as assets_mod
from app.config import settings
from app.database import get_database
from app.main import app
from app.models.common import utcnow
from app.models.user import UserInDB
from app.services.storage_service import get_storage
from app.utils.dependencies import get_current_user
from tests.conftest import TEST_DB_NAME

WS = ObjectId()
OWNER = ObjectId()


@pytest.mark.asyncio
async def test_an_uppercase_asset_id_removes_the_vectors_and_files(test_db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    get_storage.cache_clear()
    await test_db.workspaces.insert_one({
        "_id": WS, "owner_id": OWNER, "name": "V", "slug": "v", "brand_profile": {},
        "vector_namespace": str(WS), "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim, "asset_count": 1, "ready_chunk_count": 0,
        "created_at": utcnow(), "updated_at": utcnow(),
    })
    aid = ObjectId()
    await test_db.assets.insert_one({"_id": aid, "workspace_id": WS, "ingestion_status": "ready"})

    calls = {}

    class SpyStore:
        async def delete_asset(self, namespace, asset_id):
            calls["vectors"] = asset_id

    class SpyStorage:
        async def delete_prefix(self, prefix):
            calls["prefix"] = prefix

    monkeypatch.setattr(assets_mod, "get_vector_store", lambda: SpyStore())
    monkeypatch.setattr(assets_mod, "get_storage", lambda: SpyStorage())
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[get_current_user] = lambda: UserInDB(
        id=str(OWNER), email="o@e.com", hashed_password="x", full_name="O", is_demo=False
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.delete(f"/api/workspaces/{WS}/assets/{str(aid).upper()}")
    finally:
        app.dependency_overrides.clear()
        get_storage.cache_clear()
    assert resp.status_code == 204
    assert calls == {"vectors": str(aid), "prefix": f"{WS}/{aid}"}
