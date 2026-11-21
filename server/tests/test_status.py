from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from pydantic import SecretStr

from app.config import settings
from app.database import get_database
from app.main import app
from app.models.generation import (
    CardGenerateRequest,
    CardTemplate,
    DocumentArchetype,
    DocumentGenerateRequest,
    Length,
    PostPackGenerateRequest,
    TextGenerateRequest,
    Tone,
)
from app.prompts import document as document_prompt
from app.prompts import image_card, post_pack, text_post
from app.prompts.exemplars import build_exemplar_guidance
from app.routes import status as status_route
from app.services import ai_service as ai
from app.services.ai_ledger import BudgetSnapshot
from app.services.retrieval_service import PINNED_KINDS, PINNED_LIMIT
from seed import seed_demo


@pytest.fixture(autouse=True)
def _fresh_cache():
    status_route.clear_status_cache()
    yield
    status_route.clear_status_cache()


@pytest_asyncio.fixture
async def client():
    app.dependency_overrides[get_database] = lambda: object()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c
    app.dependency_overrides.pop(get_database, None)


def _snapshot(monkeypatch, allowance, spent, calls):
    async def fake(db, *, now=None):
        calls.append(1)
        return BudgetSnapshot(allowance_today=allowance, spent_today=spent, left_this_month=1)

    monkeypatch.setattr(status_route, "budget_snapshot", fake)


async def test_budget_zero_is_off_and_never_reads_the_database(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_monthly_budget_usd", Decimal(0))
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "turnstile_site_key", "")
    monkeypatch.setattr(settings, "turnstile_secret_key", SecretStr(""))
    calls: list[int] = []
    _snapshot(monkeypatch, 0, 0, calls)
    r = await client.get("/api/status")
    assert r.json() == {
        "live_ai_available": False,
        "live_ai_reason": "off",
        "turnstile_site_key": "1x00000000000000000000AA",
        "password_login": True,
    }
    assert calls == []


def test_the_threshold_is_the_largest_action_on_sonnet():
    # A document or a LinkedIn post: 8,000 output tokens and up to 21,000 input tokens.
    assert status_route.LARGEST_ACTION_OUTPUT_TOKENS == 8_000
    assert status_route.status_min_room_micros() == 122_000


def test_the_threshold_follows_the_model_price(monkeypatch):
    monkeypatch.setattr(settings, "ai_model", "claude-opus-5-5")
    assert status_route.status_min_room_micros() == 244_000


def _brief_max_length() -> int:
    lengths = {
        next(m.max_length for m in model.model_fields["brief"].metadata if hasattr(m, "max_length"))
        for model in (
            TextGenerateRequest,
            CardGenerateRequest,
            DocumentGenerateRequest,
            PostPackGenerateRequest,
        )
    }
    assert len(lengths) == 1
    return lengths.pop()


def _worst_case_context() -> list[dict]:
    """What retrieval hands the prompts at most on the demo corpus: the PINNED_LIMIT largest
    pinned voice and pillar chunks, then the k=6 largest of everything left (a pinned chunk
    over the limit can still come back as a semantic hit)."""
    chunks = seed_demo.corpus_chunks(
        "ns", {filename: f"a{i}" for i, (filename, _, _) in enumerate(seed_demo.CORPUS)}
    )

    def size(c):
        return len(c["text"].encode("utf-8"))

    by_size = sorted(chunks, key=size, reverse=True)
    pinned = [c for c in by_size if c["metadata"].get("asset_kind") in PINNED_KINDS][:PINNED_LIMIT]
    pinned_ids = {c["id"] for c in pinned}
    others = [c for c in by_size if c["id"] not in pinned_ids][:6]
    return [dict(c, score=1.0) for c in pinned + others]


def _largest_generation_reservation() -> int:
    """The largest reservation any generation route makes, built with the routes' own
    prompt and line helpers, a maximum-length brief of 4-byte characters, and the worst-case
    retrieved context."""
    brief = "\U0001F331" * _brief_max_length()
    ctx = _worst_case_context()
    voice = seed_demo.VERDURE_BRAND_PROFILE["voice_summary"]
    guide = build_exemplar_guidance([note for _, _, note in seed_demo._EXEMPLAR_CARDS])

    def total(lines):
        return sum(line.reserved_micros for line in lines)

    text = [
        total([ai.text_line(text_post.build_system(voice, guide), text_post.build_user(brief, t, n, ctx))])
        for t in Tone
        for n in Length
    ]
    card = [
        total([
            ai.card_copy_line(
                image_card.build_copy_system(voice, guide), image_card.build_copy_user(brief, tpl, t, ctx)
            ),
            ai.card_fields_line(
                image_card.build_fields_system(),
                image_card.build_fields_user(brief, tpl, ""),
                after_max_tokens=ai.CARD_COPY_MAX_TOKENS,
            ),
        ])
        for tpl in CardTemplate
        for t in Tone
    ]
    post = [
        total([
            ai.text_line(
                text_post.build_system(voice, guide),
                text_post.build_user(brief, t, Length.medium, ctx),
                purpose="post_caption",
            ),
            ai.card_fields_line(
                post_pack.build_distill_system(),
                post_pack.build_distill_user(brief, tpl, ""),
                after_max_tokens=ai.MAX_TOKENS,
                purpose="post_card_fields",
            ),
        ])
        for tpl in CardTemplate
        for t in Tone
    ]
    doc = [
        total([
            ai.document_copy_line(
                document_prompt.build_copy_system(voice), document_prompt.build_copy_user(brief, a, t, ctx)
            ),
            ai.document_sections_line(
                document_prompt.build_fields_system(), document_prompt.build_fields_user(brief, a, "")
            ),
        ])
        for a in DocumentArchetype
        for t in Tone
    ]
    return max(text + card + post + doc)


def test_the_threshold_covers_the_largest_real_reservation():
    # Built from the real prompts and line helpers, so a longer prompt, a bigger brief
    # limit, more pinned chunks, or a new token cap fails here instead of drifting.
    largest = _largest_generation_reservation()
    assert largest <= status_route.status_min_room_micros()
    assert largest > 100_000  # the build really is the worst case, not an empty prompt


async def test_room_under_the_largest_action_is_paused(client, monkeypatch):
    # Room for a text post ($0.054) but not the largest generation ($0.122): paused.
    _snapshot(monkeypatch, 1_000_000, 878_001, [])
    r = await client.get("/api/status")
    assert r.json()["live_ai_available"] is False
    assert r.json()["live_ai_reason"] == "paused"


async def test_enough_room_is_available(client, monkeypatch):
    _snapshot(monkeypatch, 1_000_000, 878_000, [])
    r = await client.get("/api/status")
    assert r.json()["live_ai_available"] is True
    assert r.json()["live_ai_reason"] == "available"


async def test_a_second_call_within_30_seconds_does_not_read_the_database(client, monkeypatch):
    calls: list[int] = []
    _snapshot(monkeypatch, 1_000_000, 0, calls)
    await client.get("/api/status")
    r = await client.get("/api/status")
    assert len(calls) == 1
    assert r.json()["live_ai_available"] is True


async def test_the_cache_expires_after_30_seconds(client, monkeypatch):
    calls: list[int] = []
    _snapshot(monkeypatch, 1_000_000, 0, calls)
    clock = [1_000.0]
    monkeypatch.setattr(status_route.time, "monotonic", lambda: clock[0])
    await client.get("/api/status")
    clock[0] += 31
    await client.get("/api/status")
    assert len(calls) == 2


async def test_cache_control_header(client, monkeypatch):
    _snapshot(monkeypatch, 1_000_000, 0, [])
    r = await client.get("/api/status")
    assert r.headers["cache-control"] == "public, max-age=30"


async def test_development_with_blank_keys_shows_the_test_site_key(client, monkeypatch):
    _snapshot(monkeypatch, 1_000_000, 0, [])
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "turnstile_site_key", "")
    monkeypatch.setattr(settings, "turnstile_secret_key", SecretStr(""))
    body = (await client.get("/api/status")).json()
    assert body["turnstile_site_key"] == "1x00000000000000000000AA"
    assert body["password_login"] is True


async def test_production_closes_password_login_and_shows_the_real_site_key(client, monkeypatch):
    _snapshot(monkeypatch, 1_000_000, 0, [])
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "turnstile_site_key", "0x4AAAAAAAreal")
    monkeypatch.setattr(settings, "turnstile_secret_key", SecretStr("0x4AAAAAAAreal-secret"))
    body = (await client.get("/api/status")).json()
    assert body["turnstile_site_key"] == "0x4AAAAAAAreal"
    assert body["password_login"] is False
