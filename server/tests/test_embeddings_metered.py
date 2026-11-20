"""Every OpenAI embedding call goes through the AI dollar ledger: retrieval (before the
model-call reservation), ingestion, and the seed's corpus step. A refusal spends nothing."""
from decimal import Decimal

import httpx
import openai
import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

import app.database as database_mod
import app.routes.documents as documents_mod
import app.routes.generate as generate_mod
import app.services.ingestion_service as ing
from app.config import settings
from app.database import get_database
from app.main import app
from app.models.common import utcnow
from app.models.user import UserInDB
from app.rag.embeddings import embed_metered, get_embedder
from app.services import storage_service
from app.services.ai_meter import embedding_line, reserve_action
from app.services.ai_service import GenerationService
from app.utils.dependencies import get_current_user
from app.utils.errors import (
    INGEST_PAUSED_COPY,
    LIVE_AI_PAUSED_COPY,
    LIVE_AI_UNAVAILABLE_COPY,
    LiveAIUnavailable,
)
from tests.conftest import NS_A, TEST_DB_NAME, build_corpus_chunks
from tests.fakes import FakeGenerationService, FakeVectorStore

WS_OID = ObjectId()
OWNER_OID = ObjectId()
WS = f"/api/workspaces/{WS_OID}"
CARD_BODY = {"brief": "Hempcrete embodied carbon", "template_id": "statement", "tone": "default"}
BRIEF = CARD_BODY["brief"]


def _openai_error(cls, status: int, code: str | None = None):
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.openai.com/v1/embeddings"))
    body = {"code": code, "message": "x"} if code else None
    return cls("x", response=response, body=body)


def _timeout():
    return openai.APITimeoutError(request=httpx.Request("POST", "https://api.openai.com/v1/embeddings"))


async def _line(db, texts):
    action = await reserve_action(db, [embedding_line("retrieval", texts)], visitor_id=None)
    return action, action.lines[0]


async def _calls(db) -> list[dict]:
    return await db.ai_spend_calls.find({}).sort("created_at", 1).to_list(None)


async def test_embedding_settles_from_the_reported_tokens(test_db, fake_embedder):
    text = "x" * 4_000  # FakeEmbedder reports len // 4 = 1,000 tokens
    action, line = await _line(test_db, [text])
    async with action:
        vectors = await embed_metered([text], line=line)
    assert len(vectors) == 1 and len(vectors[0]) == 8
    (call,) = await _calls(test_db)
    assert call["status"] == "settled" and call["outcome"] == "ok"
    assert call["actual_micros"] == 20  # 1,000 tokens x $0.02 per million


@pytest.mark.parametrize(
    "exc",
    [
        _openai_error(openai.RateLimitError, 429, "insufficient_quota"),
        _openai_error(openai.RateLimitError, 429, "credit_balance_exhausted"),
        _openai_error(openai.AuthenticationError, 401),
        _openai_error(openai.PermissionDeniedError, 403),
        _openai_error(openai.BadRequestError, 400),
    ],
)
async def test_openai_limit_and_auth_errors_settle_to_zero_and_read_plainly(
    test_db, fake_embedder, exc
):
    def boom(texts):
        raise exc

    fake_embedder.embed_with_usage = boom  # type: ignore[method-assign]
    action, line = await _line(test_db, ["hello there"])
    with pytest.raises(LiveAIUnavailable) as raised:
        async with action:
            await embed_metered(["hello there"], line=line)
    assert raised.value.message == LIVE_AI_UNAVAILABLE_COPY
    (call,) = await _calls(test_db)
    assert call["status"] == "settled" and call["actual_micros"] == 0


@pytest.mark.parametrize(
    "exc", [_timeout(), openai.APIConnectionError(request=httpx.Request("POST", "https://x"))]
)
async def test_openai_timeouts_keep_the_reservation(test_db, fake_embedder, exc):
    def boom(texts):
        raise exc

    fake_embedder.embed_with_usage = boom  # type: ignore[method-assign]
    action, line = await _line(test_db, ["hello there"])
    with pytest.raises(LiveAIUnavailable):
        async with action:
            await embed_metered(["hello there"], line=line)
    (call,) = await _calls(test_db)
    assert call["status"] == "settled" and call["outcome"] == "canceled_or_unknown"
    assert call["actual_micros"] == call["reserved_micros"] > 0


async def test_a_missing_openai_key_settles_to_zero_and_reads_plainly(test_db, monkeypatch):
    """Empty key (as in CI and the local production compose): the SDK refuses to build a
    client, no request is made, so the line is unbilled and the visitor sees the friendly copy."""
    from pydantic import SecretStr

    from app.services import ai_clients

    monkeypatch.setattr(settings, "openai_api_key", SecretStr(""))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # The autouse fixture swaps in a fake; this test needs the real embedder.
    monkeypatch.setattr("app.rag.embeddings.get_embedder", get_embedder)
    ai_clients.get_openai.cache_clear()
    get_embedder.cache_clear()
    try:
        action, line = await _line(test_db, ["hello there"])
        with pytest.raises(LiveAIUnavailable) as raised:
            async with action:
                await embed_metered(["hello there"], line=line)
    finally:
        ai_clients.get_openai.cache_clear()
        get_embedder.cache_clear()
    assert raised.value.message == LIVE_AI_UNAVAILABLE_COPY
    (call,) = await _calls(test_db)
    assert call["status"] == "settled" and call["actual_micros"] == 0


def _user() -> UserInDB:
    return UserInDB(id=str(OWNER_OID), email="o@e.com", hashed_password="x", full_name="O", is_demo=False)


@pytest_asyncio.fixture
async def client(test_db, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    storage_service.get_storage.cache_clear()
    await test_db.workspaces.insert_one(
        {
            "_id": WS_OID,
            "owner_id": OWNER_OID,
            "name": "Verdure",
            "slug": "verdure",
            "brand_profile": {"voice_summary": "Grounded, data-first voice.", "exemplars": []},
            "vector_namespace": NS_A,
            "embedding_model": settings.embedding_model,
            "embedding_dim": settings.embedding_dim,
            "asset_count": 5,
            "ready_chunk_count": 12,
            "created_at": utcnow(),
            "updated_at": utcnow(),
        }
    )
    store = FakeVectorStore()
    await store.upsert_chunks(NS_A, build_corpus_chunks(NS_A))
    monkeypatch.setattr(generate_mod, "get_vector_store", lambda: store)
    monkeypatch.setattr(documents_mod, "get_vector_store", lambda: store)
    fake_gen = FakeGenerationService()
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[GenerationService] = lambda: fake_gen
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        ac.fake_gen = fake_gen  # type: ignore[attr-defined]
        yield ac
    app.dependency_overrides.clear()
    storage_service.get_storage.cache_clear()


async def test_card_generation_meters_the_query_embedding(client, test_db, fake_embedder):
    resp = await client.post(f"{WS}/generate/card", json=CARD_BODY)
    assert resp.status_code == 200, resp.text
    calls = await _calls(test_db)
    # Retrieval is its own action, reserved before the two model calls.
    assert [c["purpose"] for c in calls][0] == "retrieval"
    assert sorted(c["purpose"] for c in calls) == ["card_copy", "card_fields", "retrieval"]
    assert all(c["status"] == "settled" and c["outcome"] == "ok" for c in calls)
    retrieval = calls[0]
    assert retrieval["provider"] == "openai"
    assert fake_embedder.calls == [[BRIEF]]


async def test_a_zero_budget_spends_nothing_on_retrieval(client, test_db, monkeypatch, fake_embedder):
    monkeypatch.setattr(settings, "ai_monthly_budget_usd", Decimal(0))
    resp = await client.post(f"{WS}/generate/card", json=CARD_BODY)
    assert resp.status_code == 429, resp.text
    assert resp.json()["detail"] == LIVE_AI_PAUSED_COPY
    assert fake_embedder.calls == []
    assert await _calls(test_db) == []


async def test_an_embedding_failure_in_retrieval_reads_plainly(client, test_db, fake_embedder):
    def boom(texts):
        raise _timeout()

    fake_embedder.embed_with_usage = boom  # type: ignore[method-assign]
    resp = await client.post(f"{WS}/generate/card", json=CARD_BODY)
    assert resp.status_code == 503, resp.text
    assert resp.json()["detail"] == LIVE_AI_UNAVAILABLE_COPY
    assert client.fake_gen.calls == []


class _FakeStorage:
    def local_path(self, key: str) -> str:
        return "/tmp/unused"


async def _seed_asset(db) -> str:
    oid = ObjectId()
    now = utcnow()
    await db.assets.insert_one(
        {
            "_id": oid, "workspace_id": ObjectId(), "filename": "voice.md",
            "content_type": "text/markdown", "asset_kind": "voice", "storage_key": "k",
            "size_bytes": 1, "ingestion_status": "processing", "chunk_count": 0,
            "error": None, "ingested_at": None, "created_at": now, "updated_at": now,
        }
    )
    return str(oid)


def _wire_ingestion(monkeypatch, test_db, store):
    async def _db():
        return test_db

    monkeypatch.setattr(ing, "get_database", _db)
    monkeypatch.setattr(ing, "get_storage", lambda: _FakeStorage())
    monkeypatch.setattr(ing, "get_vector_store", lambda: store)
    monkeypatch.setattr(
        ing, "load_sections", lambda path, ct: [ing.Section(text="Grounded, data-first voice.", page=None)]
    )
    monkeypatch.setattr(database_mod.db, "client", test_db.client)


async def test_ingestion_meters_its_embedding(test_db, monkeypatch, fake_embedder):
    store = FakeVectorStore()
    _wire_ingestion(monkeypatch, test_db, store)
    asset_id = await _seed_asset(test_db)
    await ing.ingest_asset(asset_id, "ns")
    doc = await test_db.assets.find_one({"_id": ObjectId(asset_id)})
    assert doc["ingestion_status"] == "ready"
    (call,) = await _calls(test_db)
    assert call["purpose"] == "ingest" and call["status"] == "settled"
    assert call["visitor_id"] is None
    assert len(fake_embedder.calls) == 1


async def test_ingestion_is_refused_cleanly_when_the_budget_is_used(test_db, monkeypatch, fake_embedder):
    monkeypatch.setattr(settings, "ai_monthly_budget_usd", Decimal(0))
    store = FakeVectorStore()
    _wire_ingestion(monkeypatch, test_db, store)
    asset_id = await _seed_asset(test_db)
    await ing.ingest_asset(asset_id, "ns")
    doc = await test_db.assets.find_one({"_id": ObjectId(asset_id)})
    assert doc["ingestion_status"] == "error"
    assert doc["error"] == INGEST_PAUSED_COPY
    assert fake_embedder.calls == []
    assert await store.query("ns", "voice", [0.0] * 8) == []


async def test_ingestion_reads_a_provider_failure_plainly(test_db, monkeypatch, fake_embedder):
    def boom(texts):
        raise _timeout()

    fake_embedder.embed_with_usage = boom  # type: ignore[method-assign]
    _wire_ingestion(monkeypatch, test_db, FakeVectorStore())
    asset_id = await _seed_asset(test_db)
    await ing.ingest_asset(asset_id, "ns")
    doc = await test_db.assets.find_one({"_id": ObjectId(asset_id)})
    assert doc["ingestion_status"] == "error"
    assert doc["error"] == LIVE_AI_UNAVAILABLE_COPY


