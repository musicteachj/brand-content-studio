"""Integration: the /generate/text SSE route. Empty corpus is blocked before
Claude is called; a successful generation streams frames and persists the
retrieved chunk ids + retrieval snapshot."""
import json

import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

import app.routes.generate as generate_mod
from app.config import settings
from app.database import get_database
from app.main import app
from app.services.generation_service import GenerationService
from app.utils.dependencies import get_workspace_or_404
from tests.conftest import NS_A, TEST_DB_NAME, build_corpus_chunks
from tests.fakes import FakeGenerationService, FakeVectorStore

WORKSPACE_OID = ObjectId()
OWNER_OID = ObjectId()


def _workspace(ready_chunk_count: int) -> dict:
    return {
        "_id": WORKSPACE_OID,
        "owner_id": OWNER_OID,
        "vector_namespace": NS_A,
        "ready_chunk_count": ready_chunk_count,
        "brand_profile": {"voice_summary": "Grounded, data-first voice."},
    }


@pytest_asyncio.fixture
async def client(test_db, monkeypatch):
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    store = FakeVectorStore()
    await store.upsert_chunks(NS_A, build_corpus_chunks(NS_A))
    monkeypatch.setattr(generate_mod, "get_vector_store", lambda: store)

    fake_gen = FakeGenerationService()
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[GenerationService] = lambda: fake_gen
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.fake_gen = fake_gen  # type: ignore[attr-defined]
        yield ac
    app.dependency_overrides.clear()


def _override_workspace(ready_chunk_count: int) -> None:
    app.dependency_overrides[get_workspace_or_404] = lambda: _workspace(ready_chunk_count)


URL = f"/api/workspaces/{WORKSPACE_OID}/generate/text"


@pytest.mark.asyncio
async def test_empty_corpus_blocks_generation(client):
    _override_workspace(ready_chunk_count=0)
    resp = await client.post(URL, json={"brief": "Write about hempcrete", "tone": "default", "length": "medium"})
    assert resp.status_code == 409
    # Claude must not have been called.
    assert client.fake_gen.calls == []


@pytest.mark.asyncio
async def test_generate_text_persists_retrieved_chunk_ids(client, test_db):
    _override_workspace(ready_chunk_count=12)
    resp = await client.post(
        URL, json={"brief": "Write about hempcrete embodied carbon", "tone": "default", "length": "medium"}
    )
    assert resp.status_code == 200

    # Parse the SSE frames: text deltas, a terminal meta, then [DONE].
    frames = [
        line[len("data: ") :]
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    assert frames[-1] == "[DONE]"
    texts = [json.loads(f) for f in frames if f != "[DONE]"]
    assert any("text" in t for t in texts), "expected streamed text frames"
    meta_frames = [t["meta"] for t in texts if "meta" in t]
    assert len(meta_frames) == 1
    meta = meta_frames[0]
    assert meta["retrieval"]["retrieved"], "debug panel payload present"
    assert client.fake_gen.calls, "Claude (fake) was called"

    # A generation was persisted with the retrieved chunk ids + snapshot.
    doc = await test_db.generations.find_one({"_id": ObjectId(meta["generation_id"])})
    assert doc is not None
    assert doc["type"] == "text"
    assert doc["status"] == "complete"
    assert doc["retrieved_chunk_ids"], "retrieved chunk ids persisted"
    assert doc["retrieval_meta"], "retrieval snapshot persisted"
    assert doc["output"]["post_text"]
