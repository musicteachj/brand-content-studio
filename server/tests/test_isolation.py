"""Phase 6 PR-A — end-to-end tenancy: owner A's token cannot read owner B's
workspace data. Complements the unit-level test_query_is_workspace_scoped."""
import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
from app.main import app
from app.models.user import UserInDB
from app.utils.dependencies import get_current_user
from tests.conftest import TEST_DB_NAME

OWNER_A = ObjectId()
OWNER_B = ObjectId()
WS_B = ObjectId()


def _user_a() -> UserInDB:
    return UserInDB(id=str(OWNER_A), email="a@example.com", hashed_password="x", full_name="A")


async def _seed_ws_b(db):
    await db.workspaces.insert_one(
        {
            "_id": WS_B, "owner_id": OWNER_B, "name": "B", "slug": "b", "brand_profile": {},
            "vector_namespace": str(WS_B), "embedding_model": settings.embedding_model,
            "embedding_dim": settings.embedding_dim, "asset_count": 0, "ready_chunk_count": 0,
        }
    )
    await db.assets.insert_one(
        {
            "_id": ObjectId(), "workspace_id": WS_B, "filename": "b.md",
            "content_type": "text/markdown", "asset_kind": "other", "storage_key": "k",
            "size_bytes": 1, "ingestion_status": "ready", "chunk_count": 1, "error": None,
            "ingested_at": None, "created_at": None, "updated_at": None,
        }
    )


@pytest_asyncio.fixture
async def client_a(test_db, monkeypatch):
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    await _seed_ws_b(test_db)
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[get_current_user] = lambda: _user_a()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.parametrize("path", ["", "/assets", "/generations", "/templates"])
@pytest.mark.asyncio
async def test_owner_a_cannot_read_owner_b(client_a, path):
    resp = await client_a.get(f"/api/workspaces/{WS_B}{path}")
    assert resp.status_code == 404  # never B's data leaked
