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
from app.models.user import UserInDB
from app.services.ai_service import GenerationService
from app.utils.dependencies import get_current_user, get_workspace_or_404
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
    # The demo-quota dependency resolves get_current_user directly; provide a
    # non-demo owner so it short-circuits (these tests mock get_workspace_or_404).
    app.dependency_overrides[get_current_user] = lambda: UserInDB(
        id=str(OWNER_OID), email="o@e.com", hashed_password="x", full_name="O", is_demo=False
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.fake_gen = fake_gen  # type: ignore[attr-defined]
        yield ac
    app.dependency_overrides.clear()


def _override_workspace(ready_chunk_count: int) -> None:
    app.dependency_overrides[get_workspace_or_404] = lambda: _workspace(ready_chunk_count)


URL = f"/api/workspaces/{WORKSPACE_OID}/generate/text"
CARD_URL = f"/api/workspaces/{WORKSPACE_OID}/generate/card"
POST_URL = f"/api/workspaces/{WORKSPACE_OID}/generate/post"


def _sse_frames(text: str) -> list[str]:
    return [
        line[len("data: ") :]
        for line in text.splitlines()
        if line.startswith("data: ")
    ]


def _workspace_with_exemplars() -> dict:
    return {
        "_id": WORKSPACE_OID,
        "owner_id": OWNER_OID,
        "vector_namespace": NS_A,
        "ready_chunk_count": 12,
        "brand_profile": {
            "voice_summary": "Grounded, data-first voice.",
            "exemplars": [
                {
                    "id": "e1",
                    "storage_key": "k",
                    "url": None,
                    "style_note": "Punchy hook, earthy photography.",
                }
            ],
        },
    }


@pytest.mark.asyncio
async def test_text_generation_injects_exemplar_guidance(client):
    app.dependency_overrides[get_workspace_or_404] = lambda: _workspace_with_exemplars()
    resp = await client.post(
        URL, json={"brief": "hempcrete", "tone": "default", "length": "medium"}
    )
    assert resp.status_code == 200
    system_prompt = client.fake_gen.calls[0][0]  # (system, user) of stream_text
    assert "Punchy hook, earthy photography." in system_prompt
    assert "examples to emulate" in system_prompt.lower()


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


@pytest.mark.asyncio
async def test_empty_corpus_blocks_card_generation(client):
    _override_workspace(ready_chunk_count=0)
    resp = await client.post(
        CARD_URL, json={"brief": "Hempcrete", "template_id": "photo-led", "tone": "default"}
    )
    assert resp.status_code == 409
    assert client.fake_gen.calls == []  # Claude must not have been called


@pytest.mark.asyncio
async def test_generate_card_streams_copy_then_persists_fields(client, test_db):
    _override_workspace(ready_chunk_count=12)
    resp = await client.post(
        CARD_URL,
        json={"brief": "Hempcrete embodied carbon", "template_id": "statement", "tone": "confident"},
    )
    assert resp.status_code == 200

    frames = _sse_frames(resp.text)
    assert frames[-1] == "[DONE]"
    payloads = [json.loads(f) for f in frames if f != "[DONE]"]
    assert any("text" in p for p in payloads), "copy streamed as text frames"

    meta_frames = [p["meta"] for p in payloads if "meta" in p]
    assert len(meta_frames) == 1
    meta = meta_frames[0]
    assert meta["template_id"] == "statement"
    assert meta["fields"]["headline"], "structured fields returned via tool-use"
    assert meta["suggested_keywords"], "image keywords returned"
    assert meta["retrieval"]["retrieved"], "retrieval debug payload present"
    assert client.fake_gen.card_field_calls, "tool-use extraction was called"

    # Persisted as a card generation, image null until selected, keywords stored.
    doc = await test_db.generations.find_one({"_id": ObjectId(meta["generation_id"])})
    assert doc is not None
    assert doc["type"] == "card"
    assert doc["status"] == "complete"
    assert doc["output"]["template_id"] == "statement"
    assert doc["output"]["fields"]["headline"]
    assert doc["output"]["image"] is None
    assert doc["output"]["suggested_keywords"]
    assert doc["retrieved_chunk_ids"], "retrieved chunk ids persisted"


@pytest.mark.asyncio
async def test_empty_corpus_blocks_post_pack(client):
    _override_workspace(ready_chunk_count=0)
    resp = await client.post(POST_URL, json={"brief": "Hempcrete", "tone": "default"})
    assert resp.status_code == 409
    assert client.fake_gen.calls == []  # Claude must not have been called


@pytest.mark.asyncio
async def test_generate_post_streams_caption_then_distills_card(client, test_db):
    _override_workspace(ready_chunk_count=12)
    resp = await client.post(
        POST_URL,
        json={"brief": "Hempcrete embodied carbon", "tone": "confident", "template_id": "photo-led"},
    )
    assert resp.status_code == 200

    frames = _sse_frames(resp.text)
    assert frames[-1] == "[DONE]"
    payloads = [json.loads(f) for f in frames if f != "[DONE]"]
    assert any("text" in p for p in payloads), "caption streamed as text frames"

    meta_frames = [p["meta"] for p in payloads if "meta" in p]
    assert len(meta_frames) == 1
    meta = meta_frames[0]
    assert meta["template_id"] == "photo-led"
    assert meta["fields"]["headline"], "card fields distilled via tool-use"
    assert meta["suggested_keywords"], "image keywords returned"
    assert meta["retrieval"]["retrieved"], "retrieval debug payload present"
    assert client.fake_gen.calls, "caption (stream_text) was called"
    assert client.fake_gen.card_field_calls, "card distillation (tool-use) was called"

    # Persisted as a post_pack: caption at top, card nested, image null until PATCH.
    doc = await test_db.generations.find_one({"_id": ObjectId(meta["generation_id"])})
    assert doc is not None
    assert doc["type"] == "post_pack"
    assert doc["status"] == "complete"
    assert doc["output"]["post_text"], "caption persisted"
    assert isinstance(doc["output"]["hashtags"], list)
    assert doc["output"]["card"]["template_id"] == "photo-led"
    assert doc["output"]["card"]["fields"]["headline"]
    assert doc["output"]["card"]["image"] is None
    assert doc["output"]["card"]["suggested_keywords"]
    assert doc["retrieved_chunk_ids"], "retrieved chunk ids persisted"
