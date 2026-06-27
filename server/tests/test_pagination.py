"""Phase 6 PR-A — pagination of History/Assets lists."""
import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
from app.main import app
from app.models.asset import AssetPage
from app.models.common import utcnow
from app.models.generation import GenerationCount, GenerationPage
from app.services import generations_service
from app.utils.dependencies import get_workspace_or_404
from tests.conftest import TEST_DB_NAME

WS = ObjectId()
GEN_URL = f"/api/workspaces/{WS}/generations"


def test_page_models_shape():
    gp = GenerationPage(items=[], next_offset=24)
    assert gp.next_offset == 24
    assert AssetPage(items=[], next_offset=None).next_offset is None
    assert GenerationCount(count=7).count == 7


async def _seed_generations(db, n):
    now = utcnow()
    docs = [
        {
            "_id": ObjectId(), "workspace_id": WS, "owner_id": ObjectId(), "type": "text",
            "brief": f"brief {i}", "status": "complete",
            "output": {"post_text": f"p{i}", "hashtags": [], "char_count": 2},
            "retrieved_chunk_ids": [], "retrieval_meta": [], "model": "m",
            "embedding_query_model": "e", "created_at": now, "updated_at": now,
        }
        for i in range(n)
    ]
    await db.generations.insert_many(docs)


@pytest.mark.asyncio
async def test_list_generations_paginates(test_db):
    await _seed_generations(test_db, 30)
    items, next_offset = await generations_service.list_generations(
        test_db, WS, "all", limit=24, offset=0
    )
    assert len(items) == 24
    assert next_offset == 24
    items2, next2 = await generations_service.list_generations(
        test_db, WS, "all", limit=24, offset=24
    )
    assert len(items2) == 6
    assert next2 is None


@pytest.mark.asyncio
async def test_count_generations(test_db):
    await _seed_generations(test_db, 5)
    assert await generations_service.count_generations(test_db, WS) == 5


@pytest_asyncio.fixture
async def client(test_db, monkeypatch):
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[get_workspace_or_404] = lambda: {"_id": WS, "owner_id": ObjectId()}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_generations_route_paginates(client, test_db):
    await _seed_generations(test_db, 30)
    r1 = await client.get(GEN_URL, params={"limit": 24, "offset": 0})
    assert r1.status_code == 200
    body = r1.json()
    assert len(body["items"]) == 24 and body["next_offset"] == 24
    r2 = await client.get(GEN_URL, params={"limit": 24, "offset": 24})
    assert len(r2.json()["items"]) == 6 and r2.json()["next_offset"] is None


@pytest.mark.asyncio
async def test_generations_count_route(client, test_db):
    await _seed_generations(test_db, 3)
    r = await client.get(f"{GEN_URL}/count")
    assert r.status_code == 200 and r.json()["count"] == 3


@pytest.mark.asyncio
async def test_limit_over_max_is_422(client):
    r = await client.get(GEN_URL, params={"limit": 1000})
    assert r.status_code == 422
