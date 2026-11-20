"""Every paid route goes through the AI dollar ledger: it reserves before any model call
(and before an SSE response starts), settles each call from its usage, and releases a
call that never ran. Replaces the old per-day demo count. Owner user, a ready workspace,
the fake vector store and fake model services, and the real test Mongo."""
import io
import json
from decimal import Decimal

import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient
from PIL import Image

import app.routes.documents as documents_mod
import app.routes.generate as generate_mod
from app.config import settings
from app.database import get_database
from app.main import app
from app.models.common import utcnow
from app.models.generation import CardTemplate
from app.models.user import UserInDB
from app.prompts import image_card
from app.prompts.brand_extract import (
    BRAND_EXTRACT_TOOL,
    EXEMPLAR_NOTE_TOOL,
    build_exemplar_system,
    build_exemplar_user,
    build_extract_system,
    build_extract_user,
)
from app.prompts.image_card import CARD_FIELDS_TOOL
from app.services import claude_calls, storage_service
from app.services.ai_pricing import IMAGE_TOKEN_BOUND, SCHEMA_OVERHEAD_TOKENS, estimate_tokens
from app.services.ai_service import CARD_COPY_MAX_TOKENS, CARD_FIELDS_MAX_TOKENS, GenerationService
from app.services.brand_extract_service import (
    EXTRACT_MAX_TOKENS,
    BrandExtractService,
    extract_palette,
)
from app.utils.dependencies import get_current_user
from app.utils.errors import LIVE_AI_PAUSED_COPY, NO_CONTEXT_COPY
from tests.conftest import NS_A, TEST_DB_NAME, build_corpus_chunks
from tests.fakes import FakeBrandExtractService, FakeGenerationService, FakeVectorStore
from tests.test_templates import DOCX_CT, _docx_bytes

WS_OID = ObjectId()
OWNER_OID = ObjectId()
WS = f"/api/workspaces/{WS_OID}"

TEXT_BODY = {"brief": "Write about hempcrete embodied carbon", "tone": "default", "length": "medium"}
CARD_BODY = {"brief": "Hempcrete embodied carbon", "template_id": "statement", "tone": "default"}
POST_BODY = {"brief": "Hempcrete embodied carbon", "template_id": "photo-led", "tone": "default"}
DOC_BODY = {"brief": "A one-pager on hempcrete", "archetype": "one-pager", "tone": "default"}
FILL_BODY = {"brief": "a welcome letter"}

# A fill of 4,000 micros: 1,000 input tokens x 2 + 200 output tokens x 10 (Sonnet 5.5).
FAKE_CALL_MICROS = 4_000


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (28, 58, 46)).save(buf, format="PNG")
    return buf.getvalue()


def _user(is_demo: bool = False) -> UserInDB:
    return UserInDB(id=str(OWNER_OID), email="o@e.com", hashed_password="x", full_name="O", is_demo=is_demo)


async def _seed_workspace(db) -> None:
    await db.workspaces.insert_one(
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


@pytest_asyncio.fixture
async def client(test_db, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    storage_service.get_storage.cache_clear()
    await _seed_workspace(test_db)

    store = FakeVectorStore()
    await store.upsert_chunks(NS_A, build_corpus_chunks(NS_A))
    monkeypatch.setattr(generate_mod, "get_vector_store", lambda: store)
    monkeypatch.setattr(documents_mod, "get_vector_store", lambda: store)

    fake_gen = FakeGenerationService()
    fake_extract = FakeBrandExtractService()
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[get_current_user] = lambda: _user()
    app.dependency_overrides[GenerationService] = lambda: fake_gen
    app.dependency_overrides[BrandExtractService] = lambda: fake_extract
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        ac.fake_gen = fake_gen  # type: ignore[attr-defined]
        ac.fake_extract = fake_extract  # type: ignore[attr-defined]
        ac.store = store  # type: ignore[attr-defined]
        yield ac
    app.dependency_overrides.clear()
    storage_service.get_storage.cache_clear()


async def _template_id(ac: AsyncClient) -> str:
    resp = await ac.post(
        f"{WS}/templates", files={"file": ("Report.docx", _docx_bytes("Hello {{client_name}}"), DOCX_CT)}
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def _post(ac: AsyncClient, route: str):
    """POST one paid route by name, with a valid body or upload."""
    if route in ("text", "card", "post", "document"):
        body = {"text": TEXT_BODY, "card": CARD_BODY, "post": POST_BODY, "document": DOC_BODY}[route]
        return await ac.post(f"{WS}/generate/{route}", json=body)
    if route == "ai-fill":
        return await ac.post(f"{WS}/templates/{await _template_id(ac)}/ai-fill", json=FILL_BODY)
    if route == "fill-from-document":
        return await ac.post(
            f"{WS}/templates/{await _template_id(ac)}/fill-from-document",
            files={"file": ("draft.docx", _docx_bytes("Welcome to Acme"), DOCX_CT)},
        )
    if route == "brand-extract":
        return await ac.post(f"{WS}/brand/extract", files={"file": ("logo.png", _png(), "image/png")})
    if route == "exemplars":
        return await ac.post(f"{WS}/exemplars", files={"file": ("card.png", _png(), "image/png")})
    raise AssertionError(route)


async def _calls(db) -> list[dict]:
    return await db.ai_spend_calls.find({}).sort("created_at", 1).to_list(None)


PAID = ["text", "card", "post", "document", "ai-fill", "fill-from-document", "brand-extract", "exemplars"]


@pytest.mark.parametrize("route", PAID)
async def test_a_zero_budget_refuses_every_paid_route_before_any_call(client, test_db, monkeypatch, route):
    monkeypatch.setattr(settings, "ai_monthly_budget_usd", Decimal(0))
    resp = await _post(client, route)
    assert resp.status_code == 429, resp.text
    assert resp.json() == {"detail": LIVE_AI_PAUSED_COPY, "code": "live_ai_paused"}
    assert client.fake_gen.calls == [] and client.fake_gen.card_field_calls == []
    assert client.fake_gen.doc_section_calls == [] and client.fake_gen.fill_calls == []
    assert client.fake_extract.calls == []
    assert await _calls(test_db) == []


@pytest.mark.parametrize(
    "route, purposes",
    [
        ("text", ["text_post"]),
        ("card", ["card_copy", "card_fields"]),
        ("post", ["post_caption", "post_card_fields"]),
        ("document", ["document_copy", "document_sections"]),
        ("ai-fill", ["template_fill"]),
        ("fill-from-document", ["template_fill_from_document"]),
        ("brand-extract", ["brand_extract"]),
        ("exemplars", ["exemplar_note"]),
    ],
)
async def test_each_paid_route_settles_every_call(client, test_db, route, purposes):
    resp = await _post(client, route)
    assert resp.status_code == 200, resp.text
    calls = await _calls(test_db)
    assert sorted(c["purpose"] for c in calls) == sorted(purposes)
    for c in calls:
        assert c["status"] == "settled" and c["outcome"] == "ok"
        assert c["actual_micros"] == FAKE_CALL_MICROS
        assert c["visitor_id"] is None
    day = await test_db.ai_spend_days.find_one({})
    assert day["total_micros"] == FAKE_CALL_MICROS * len(purposes)


async def test_text_generation_settles_its_one_call(client, test_db):
    resp = await client.post(f"{WS}/generate/text", json=TEXT_BODY)
    assert resp.status_code == 200
    calls = await _calls(test_db)
    assert len(calls) == 1
    assert calls[0]["status"] == "settled" and calls[0]["actual_micros"] == FAKE_CALL_MICROS


async def test_card_generation_settles_both_calls(client, test_db):
    resp = await client.post(f"{WS}/generate/card", json=CARD_BODY)
    assert resp.status_code == 200
    calls = await _calls(test_db)
    assert [c["actual_micros"] for c in calls] == [FAKE_CALL_MICROS, FAKE_CALL_MICROS]
    assert all(c["status"] == "settled" for c in calls)


async def test_an_empty_copy_releases_the_unused_fields_call(client, test_db):
    client.fake_gen.CARD_COPY = ""
    resp = await client.post(f"{WS}/generate/card", json=CARD_BODY)
    assert resp.status_code == 200
    assert "empty response" in resp.text
    by_purpose = {c["purpose"]: c for c in await _calls(test_db)}
    assert by_purpose["card_copy"]["actual_micros"] == FAKE_CALL_MICROS
    fields = by_purpose["card_fields"]
    assert (fields["status"], fields["actual_micros"], fields["outcome"]) == ("settled", 0, "not_attempted")
    day = await test_db.ai_spend_days.find_one({})
    assert day["total_micros"] == FAKE_CALL_MICROS


async def test_the_fields_call_reserves_room_for_the_whole_copy(client, test_db):
    resp = await client.post(f"{WS}/generate/card", json=CARD_BODY)
    assert resp.status_code == 200
    fields = next(c for c in await _calls(test_db) if c["purpose"] == "card_fields")
    system = claude_calls.structured_system(image_card.build_fields_system(), CARD_FIELDS_TOOL)
    user = image_card.build_fields_user(CARD_BODY["brief"], CardTemplate.statement, "")
    schema = estimate_tokens(json.dumps(CARD_FIELDS_TOOL["input_schema"])) + SCHEMA_OVERHEAD_TOKENS
    input_tokens = estimate_tokens(system) + estimate_tokens(user) + schema + CARD_COPY_MAX_TOKENS
    assert fields["reserved_micros"] == 2 * input_tokens + 10 * CARD_FIELDS_MAX_TOKENS


@pytest.mark.parametrize("route", ["text", "card", "post", "document"])
async def test_no_retrieved_context_is_a_409_before_any_reservation(client, test_db, monkeypatch, route):
    empty = FakeVectorStore()
    monkeypatch.setattr(generate_mod, "get_vector_store", lambda: empty)
    monkeypatch.setattr(documents_mod, "get_vector_store", lambda: empty)
    resp = await _post(client, route)
    assert resp.status_code == 409
    assert resp.json()["detail"] == NO_CONTEXT_COPY
    assert client.fake_gen.calls == []
    assert await _calls(test_db) == []


async def test_brand_extract_is_closed_to_the_demo(client, test_db):
    app.dependency_overrides[get_current_user] = lambda: _user(is_demo=True)
    resp = await _post(client, "brand-extract")
    assert resp.status_code == 403
    assert client.fake_extract.calls == []
    assert await _calls(test_db) == []


async def test_brand_extract_and_exemplars_reserve_for_owners(client, test_db):
    png = _png()
    assert (await _post(client, "brand-extract")).status_code == 200
    assert (await _post(client, "exemplars")).status_code == 200
    by_purpose = {c["purpose"]: c for c in await _calls(test_db)}
    assert set(by_purpose) == {"brand_extract", "exemplar_note"}

    def reserved(system: str, user: str, tool: dict) -> int:
        schema = estimate_tokens(json.dumps(tool["input_schema"])) + SCHEMA_OVERHEAD_TOKENS
        tokens = IMAGE_TOKEN_BOUND + estimate_tokens(claude_calls.structured_system(system, tool))
        tokens += estimate_tokens(user) + schema
        return 2 * tokens + 10 * EXTRACT_MAX_TOKENS

    assert by_purpose["brand_extract"]["reserved_micros"] == reserved(
        build_extract_system(), build_extract_user(extract_palette(png)), BRAND_EXTRACT_TOOL
    )
    assert by_purpose["exemplar_note"]["reserved_micros"] == reserved(
        build_exemplar_system(), build_exemplar_user(), EXEMPLAR_NOTE_TOOL
    )
    for c in by_purpose.values():
        assert c["status"] == "settled" and c["actual_micros"] == FAKE_CALL_MICROS
