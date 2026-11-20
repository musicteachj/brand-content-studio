"""Visitor sessions: a demo start behind the bot check and per-IP limits creates a
24-hour session whose ID rides in the token; a demo token without a live session is a
plain 401 `demo_ended`; password sign-in is closed in production. The real
`get_current_user` runs against the test Mongo; the bot check is answered locally."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

import app.routes.generate as generate_mod
from app.config import TURNSTILE_PASS_SECRET, settings
from app.database import get_database
from app.main import app
from app.services import storage_service
from app.services.ai_service import GenerationService
from app.services.session_service import SESSION_TTL, create_session
from app.services.turnstile import DUMMY_TOKEN, TestKeyVerifier, Verdict, get_turnstile_verifier
from app.utils.errors import (
    BOT_CHECK_FAILED_COPY,
    BOT_CHECK_UNAVAILABLE_COPY,
    DEMO_ENDED_COPY,
    RATE_LIMITED_COPY,
)
from app.utils.security import create_access_token, get_password_hash, verify_password
from tests.conftest import NS_A, TEST_DB_NAME, build_corpus_chunks
from tests.fakes import FakeGenerationService, FakeVectorStore
from tests.test_ai_routes_budget import OWNER_OID, TEXT_BODY, WS, _seed_workspace

_PASSWORD = "correct-horse-battery-staple"
_HASH = get_password_hash(_PASSWORD)


async def _seed_user(db, *, email: str, is_demo: bool, oid: ObjectId | None = None) -> ObjectId:
    now = datetime.now(timezone.utc)
    doc = {
        "email": email,
        "hashed_password": _HASH,
        "full_name": "Demo" if is_demo else "Owner",
        "is_active": True,
        "is_admin": False,
        "is_demo": is_demo,
        "created_at": now,
        "updated_at": now,
    }
    if oid is not None:
        doc["_id"] = oid
    return (await db.users.insert_one(doc)).inserted_id


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def client(test_db, monkeypatch):
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    app.dependency_overrides[get_database] = lambda: test_db
    # Cloudflare's always-pass test secret, answered locally, whatever the local .env says.
    app.dependency_overrides[get_turnstile_verifier] = lambda: TestKeyVerifier(TURNSTILE_PASS_SECRET)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _start(ac: AsyncClient, token: str = DUMMY_TOKEN):
    return await ac.post("/api/auth/demo-login", json={"turnstile_token": token})


async def test_a_demo_start_without_a_valid_token_is_refused(client, test_db):
    await _seed_user(test_db, email="demo@x.com", is_demo=True)
    for token in ("not-the-dummy-token", ""):
        resp = await _start(client, token)
        assert resp.status_code == 403
        assert resp.json() == {"detail": BOT_CHECK_FAILED_COPY, "code": "bot_check_failed"}
    # A missing token is a validation error, never a session.
    assert (await client.post("/api/auth/demo-login")).status_code == 422
    assert (await client.post("/api/auth/demo-login", json={"turnstile_token": "x" * 2049})).status_code == 422
    assert await test_db.demo_sessions.count_documents({}) == 0


async def test_a_demo_start_creates_a_24_hour_session(client, test_db):
    uid = await _seed_user(test_db, email="demo@x.com", is_demo=True)
    resp = await _start(client)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["expires_in"] == 86_400
    payload = jwt.decode(
        body["access_token"],
        settings.jwt_secret_key.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
    )
    assert payload["user_id"] == str(uid)
    assert payload["email"] == "demo@x.com"
    assert payload["exp"] - payload["iat"] == 86_400
    session = await test_db.demo_sessions.find_one({"_id": payload["sid"]})
    assert session is not None
    assert session["user_id"] == uid
    assert session["expires_at"] - session["created_at"] == timedelta(hours=24) == SESSION_TTL
    assert len(payload["sid"]) >= 40  # token_urlsafe(32)

    me = await client.get("/api/auth/me", headers=_bearer(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["is_demo"] is True

    # Each start is its own session.
    again = await _start(client)
    assert again.status_code == 200
    assert await test_db.demo_sessions.count_documents({}) == 2


class _Unavailable:
    async def verify(self, token: str, remote_ip: str | None) -> Verdict:
        return Verdict.UNAVAILABLE


async def test_an_unreachable_bot_check_is_a_503(client, test_db):
    await _seed_user(test_db, email="demo@x.com", is_demo=True)
    app.dependency_overrides[get_turnstile_verifier] = lambda: _Unavailable()
    resp = await _start(client)
    assert resp.status_code == 503
    assert resp.json() == {"detail": BOT_CHECK_UNAVAILABLE_COPY, "code": "bot_check_unavailable"}
    assert await test_db.demo_sessions.count_documents({}) == 0


async def test_an_unseeded_demo_is_a_plain_503(client):
    resp = await _start(client)
    assert resp.status_code == 503
    assert resp.json()["detail"] == "The demo isn't ready yet. Try again in a minute."


async def test_demo_starts_are_limited_per_ip_per_hour_and_per_day(
    client, test_db, monkeypatch, enabled_limiter
):
    from app.utils.ratelimit import limiter

    await _seed_user(test_db, email="demo@x.com", is_demo=True)
    monkeypatch.setattr(settings, "demo_starts_per_hour", 2)
    statuses = [(await _start(client)).status_code for _ in range(2)]
    third = await _start(client)
    assert statuses == [200, 200]
    assert third.status_code == 429
    assert third.json() == {"detail": RATE_LIMITED_COPY, "code": "rate_limited"}

    limiter.reset()
    monkeypatch.setattr(settings, "demo_starts_per_hour", 100)
    monkeypatch.setattr(settings, "demo_starts_per_day", 2)
    statuses = [(await _start(client)).status_code for _ in range(2)]
    third = await _start(client)
    assert statuses == [200, 200]
    assert third.status_code == 429
    assert third.json() == {"detail": RATE_LIMITED_COPY, "code": "rate_limited"}
    assert await test_db.demo_sessions.count_documents({}) == 4


def _assert_demo_ended(resp) -> None:
    assert resp.status_code == 401
    assert resp.json() == {"detail": DEMO_ENDED_COPY, "code": "demo_ended"}
    assert resp.headers["www-authenticate"] == "Bearer"


async def test_a_demo_token_without_a_session_claim_is_demo_ended(client, test_db):
    uid = await _seed_user(test_db, email="demo@x.com", is_demo=True)
    token = create_access_token({"user_id": str(uid), "email": "demo@x.com"})
    _assert_demo_ended(await client.get("/api/auth/me", headers=_bearer(token)))


async def test_an_expired_or_deleted_session_is_demo_ended(client, test_db):
    uid = await _seed_user(test_db, email="demo@x.com", is_demo=True)
    long_ago = datetime.now(timezone.utc) - SESSION_TTL - timedelta(minutes=1)
    expired = await create_session(test_db, user_id=uid, now=long_ago)
    token = create_access_token({"user_id": str(uid), "email": "demo@x.com", "sid": expired["_id"]})
    _assert_demo_ended(await client.get("/api/auth/me", headers=_bearer(token)))

    live = await create_session(test_db, user_id=uid)
    token = create_access_token({"user_id": str(uid), "email": "demo@x.com", "sid": live["_id"]})
    assert (await client.get("/api/auth/me", headers=_bearer(token))).status_code == 200
    await test_db.demo_sessions.delete_one({"_id": live["_id"]})
    _assert_demo_ended(await client.get("/api/auth/me", headers=_bearer(token)))

    # A session ID belongs to its own demo user only.
    other = await create_session(test_db, user_id=ObjectId())
    token = create_access_token({"user_id": str(uid), "email": "demo@x.com", "sid": other["_id"]})
    _assert_demo_ended(await client.get("/api/auth/me", headers=_bearer(token)))


async def test_owner_tokens_need_no_session(client, test_db):
    uid = await _seed_user(test_db, email="owner@x.com", is_demo=False)
    token = create_access_token({"user_id": str(uid), "email": "owner@x.com"})
    resp = await client.get("/api/auth/me", headers=_bearer(token))
    assert resp.status_code == 200
    assert resp.json()["is_demo"] is False


async def test_login_is_404_in_production_and_works_in_development(client, test_db, monkeypatch):
    await _seed_user(test_db, email="owner@x.com", is_demo=False)
    creds = {"email": "owner@x.com", "password": _PASSWORD}
    monkeypatch.setattr(settings, "environment", "production")
    assert (await client.post("/api/auth/login", json=creds)).status_code == 404
    monkeypatch.setattr(settings, "environment", "development")
    assert (await client.post("/api/auth/login", json=creds)).status_code == 200


async def test_the_seed_gives_the_demo_user_an_unusable_password_in_production(test_db, monkeypatch):
    from seed.seed_demo import _ensure_demo_user

    monkeypatch.setattr(settings, "environment", "production")
    uid = await _ensure_demo_user(test_db)
    doc = await test_db.users.find_one({"_id": uid})
    assert doc["is_demo"] is True
    assert not verify_password(settings.demo_password, doc["hashed_password"])


async def test_the_seed_rehashes_an_existing_demo_password_in_production(test_db, monkeypatch):
    from seed.seed_demo import _ensure_demo_user

    monkeypatch.setattr(settings, "environment", "development")
    uid = await _ensure_demo_user(test_db)
    doc = await test_db.users.find_one({"_id": uid})
    assert verify_password(settings.demo_password, doc["hashed_password"])  # dev keeps it

    monkeypatch.setattr(settings, "environment", "production")
    assert await _ensure_demo_user(test_db) == uid
    doc = await test_db.users.find_one({"_id": uid})
    assert not verify_password(settings.demo_password, doc["hashed_password"])
    assert await test_db.users.count_documents({"is_demo": True}) == 1


@pytest_asyncio.fixture
async def gen_client(client, test_db, monkeypatch, tmp_path):
    """The demo client plus a ready workspace owned by the demo user, the fake store, and
    the fake model service."""
    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    storage_service.get_storage.cache_clear()
    await _seed_user(test_db, email="demo@x.com", is_demo=True, oid=OWNER_OID)
    await _seed_workspace(test_db)
    store = FakeVectorStore()
    await store.upsert_chunks(NS_A, build_corpus_chunks(NS_A))
    monkeypatch.setattr(generate_mod, "get_vector_store", lambda: store)
    fake_gen = FakeGenerationService()
    app.dependency_overrides[GenerationService] = lambda: fake_gen
    yield client
    storage_service.get_storage.cache_clear()


@pytest.mark.usefixtures("gen_client")
async def test_the_ledger_counts_spend_per_session(client, test_db):
    started = await _start(client)
    assert started.status_code == 200, started.text
    token = started.json()["access_token"]
    sid = jwt.decode(
        token, settings.jwt_secret_key.get_secret_value(), algorithms=[settings.jwt_algorithm]
    )["sid"]

    resp = await client.post(f"{WS}/generate/text", json=TEXT_BODY, headers=_bearer(token))
    assert resp.status_code == 200, resp.text

    calls = await test_db.ai_spend_calls.find({}).to_list(None)
    assert calls and all(c["visitor_id"] == sid for c in calls)
    visitor = await test_db.ai_spend_visitors.find_one({"_id": sid})
    assert visitor is not None
    assert visitor["total_micros"] == sum(c["actual_micros"] for c in calls) > 0
