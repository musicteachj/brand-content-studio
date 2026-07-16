"""The authentication path — the audit's highest-value test gap (TEST-01).

Every *route* test overrides `get_current_user`, so before this file the real
token→user path, `authenticate_user`, and `utils/security.py` were never exercised.
Here the real dependency runs: security helpers are unit-tested (no DB); the service,
dependency, and routes are integration-tested against the local docker Mongo (skips
cleanly when it's down, per `test_db`). The limiter is disabled globally in conftest,
so these never hit 429 (rate limiting is covered in test_rate_limit.py).

Authorization (tenancy) is deliberately out of scope — it's already covered for real
in test_isolation.py. This file is about *authentication*.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import pytest_asyncio
from bson import ObjectId
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
from app.main import app
from app.models.user import UserInDB
from app.services.auth_service import authenticate_user, get_user_by_id
from app.utils.dependencies import get_current_user
from app.utils.security import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)

# One bcrypt hash for the whole module (bcrypt is ~230ms/call); seeded users reuse it.
_PASSWORD = "correct-horse-battery-staple"
_HASH = get_password_hash(_PASSWORD)


# --------------------------------------------------------------------------- helpers
async def _seed_user(
    db,
    *,
    email: str = "owner@example.com",
    hashed_password: str = _HASH,
    full_name: str = "Owner",
    is_active: bool = True,
    is_admin: bool = False,
    is_demo: bool = False,
) -> ObjectId:
    now = datetime.now(timezone.utc)
    res = await db.users.insert_one(
        {
            "email": email,
            "hashed_password": hashed_password,
            "full_name": full_name,
            "is_active": is_active,
            "is_admin": is_admin,
            "is_demo": is_demo,
            "created_at": now,
            "updated_at": now,
        }
    )
    return res.inserted_id


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _b64url(obj: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


def _alg_none_token(payload: dict) -> str:
    """A classic `alg:none` forgery — header claims no signature, sig segment empty."""
    return f"{_b64url({'alg': 'none', 'typ': 'JWT'})}.{_b64url(payload)}."


def _flip_signature(token: str) -> str:
    """Return `token` with one signature byte changed (breaks the HMAC)."""
    head, payload, sig = token.split(".")
    repl = "A" if sig[0] != "A" else "B"
    return f"{head}.{payload}.{repl}{sig[1:]}"


@pytest_asyncio.fixture
async def client(test_db):
    """AsyncClient wired to the app, with the DB pointed at the clean test database.
    `get_current_user` is intentionally NOT overridden — that's the whole point."""
    app.dependency_overrides[get_database] = lambda: test_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# =========================================================== utils/security.py (pure)
def test_password_hash_and_verify_roundtrip():
    hashed = get_password_hash("s3cret-pw")
    assert hashed != "s3cret-pw"  # not stored in plaintext
    assert verify_password("s3cret-pw", hashed) is True
    assert verify_password("wrong-pw", hashed) is False


def test_bcrypt_truncation_at_72_bytes():
    """bcrypt uses only the first 72 bytes; _truncate mirrors that so long passwords
    don't error. A change past byte 72 is invisible; a change within it is not."""
    base = "a" * 72
    hashed = get_password_hash(base + "EXTRA-IGNORED")
    assert verify_password(base + "A-DIFFERENT-SUFFIX", hashed) is True
    assert verify_password("b" + "a" * 71 + "EXTRA-IGNORED", hashed) is False


def test_create_and_decode_access_token_roundtrip():
    token = create_access_token({"user_id": "abc", "email": "a@b.com"})
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["user_id"] == "abc"
    assert payload["email"] == "a@b.com"
    assert "exp" in payload and "iat" in payload  # create_access_token sets both


def test_decode_tampered_signature_returns_none():
    token = create_access_token({"user_id": "abc"})
    assert decode_access_token(_flip_signature(token)) is None


def test_decode_wrong_secret_returns_none():
    forged = jwt.encode(
        {"user_id": "abc", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "a-totally-different-signing-secret-value",
        algorithm=settings.jwt_algorithm,
    )
    assert decode_access_token(forged) is None


def test_decode_expired_token_returns_none():
    token = create_access_token({"user_id": "abc"}, expires_delta=timedelta(minutes=-1))
    assert decode_access_token(token) is None


def test_decode_alg_none_token_returns_none():
    # Blocked because decode pins algorithms=["HS256"] → InvalidAlgorithmError → None.
    assert decode_access_token(_alg_none_token({"user_id": "abc"})) is None


def test_decode_structural_garbage_returns_none():
    assert decode_access_token("not.a.token") is None
    assert decode_access_token("") is None


# ================================================= services/auth_service (DB-backed)
@pytest.mark.asyncio
async def test_authenticate_user_correct_password_returns_doc(test_db):
    await _seed_user(test_db, email="u@x.com")
    doc = await authenticate_user(test_db, "u@x.com", _PASSWORD)
    assert doc is not None
    assert doc["email"] == "u@x.com"
    assert "_id" in doc


@pytest.mark.asyncio
async def test_authenticate_user_wrong_password_returns_none(test_db):
    await _seed_user(test_db, email="u@x.com")
    assert await authenticate_user(test_db, "u@x.com", "not-the-password") is None


@pytest.mark.asyncio
async def test_authenticate_user_unknown_email_returns_none(test_db):
    # No user exists; the service still runs a decoy bcrypt so timing matches a real
    # check (SEC-09). We can only assert the result here, not the constant-time property.
    assert await authenticate_user(test_db, "nobody@x.com", _PASSWORD) is None


@pytest.mark.asyncio
async def test_authenticate_user_inactive_returns_none(test_db):
    await _seed_user(test_db, email="ina@x.com", is_active=False)
    assert await authenticate_user(test_db, "ina@x.com", _PASSWORD) is None


@pytest.mark.asyncio
async def test_get_user_by_id_valid_missing_and_malformed(test_db):
    uid = await _seed_user(test_db, email="byid@x.com")
    user = await get_user_by_id(test_db, str(uid))
    assert isinstance(user, UserInDB)
    assert user.id == str(uid)
    assert user.email == "byid@x.com"
    assert await get_user_by_id(test_db, str(ObjectId())) is None  # valid oid, no user
    assert await get_user_by_id(test_db, "not-an-object-id") is None  # malformed → except


# ============================== utils/dependencies.get_current_user (called directly)
@pytest.mark.asyncio
async def test_get_current_user_valid_token_returns_user(test_db):
    uid = await _seed_user(test_db, email="cur@x.com")
    token = create_access_token({"user_id": str(uid), "email": "cur@x.com"})
    user = await get_current_user(credentials=_creds(token), db=test_db)
    assert isinstance(user, UserInDB)
    assert user.id == str(uid)
    assert user.email == "cur@x.com"


@pytest.mark.asyncio
async def test_get_current_user_expired_token_401(test_db):
    # Seed a valid, ACTIVE user and expire ITS token: the 401 can then only come from
    # the expiry check. (With a bogus user_id, the lookup miss alone would 401 even if
    # expiry enforcement were removed — the test wouldn't isolate the behavior.)
    uid = await _seed_user(test_db, email="exp@x.com")
    token = create_access_token({"user_id": str(uid)}, expires_delta=timedelta(minutes=-1))
    with pytest.raises(HTTPException) as exc:
        await get_current_user(credentials=_creds(token), db=test_db)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_tampered_token_401(test_db):
    # Seed a valid, ACTIVE user and tamper ITS token: the 401 can then only come from
    # signature verification, not from an unresolvable user_id.
    uid = await _seed_user(test_db, email="tam@x.com")
    token = _flip_signature(create_access_token({"user_id": str(uid)}))
    with pytest.raises(HTTPException) as exc:
        await get_current_user(credentials=_creds(token), db=test_db)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_missing_user_id_claim_401(test_db):
    token = create_access_token({"email": "a@b.com"})  # no user_id claim
    with pytest.raises(HTTPException) as exc:
        await get_current_user(credentials=_creds(token), db=test_db)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_unknown_user_id_401(test_db):
    token = create_access_token({"user_id": str(ObjectId())})  # valid oid, no such user
    with pytest.raises(HTTPException) as exc:
        await get_current_user(credentials=_creds(token), db=test_db)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_malformed_user_id_401(test_db):
    token = create_access_token({"user_id": "not-an-object-id"})
    with pytest.raises(HTTPException) as exc:
        await get_current_user(credentials=_creds(token), db=test_db)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_inactive_user_403(test_db):
    uid = await _seed_user(test_db, email="ina@x.com", is_active=False)
    token = create_access_token({"user_id": str(uid)})
    with pytest.raises(HTTPException) as exc:
        await get_current_user(credentials=_creds(token), db=test_db)
    assert exc.value.status_code == 403


# ============================================================ routes/auth.py (via HTTP)
@pytest.mark.asyncio
async def test_login_success_returns_token(client, test_db):
    uid = await _seed_user(test_db, email="login@x.com")
    resp = await client.post(
        "/api/auth/login", json={"email": "login@x.com", "password": _PASSWORD}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.access_token_expire_minutes * 60
    payload = decode_access_token(body["access_token"])
    assert payload is not None and payload["user_id"] == str(uid)


@pytest.mark.asyncio
async def test_login_bad_password_401(client, test_db):
    await _seed_user(test_db, email="login@x.com")
    resp = await client.post(
        "/api/auth/login", json={"email": "login@x.com", "password": "wrong"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email_401(client):
    resp = await client.post(
        "/api/auth/login", json={"email": "nobody@x.com", "password": _PASSWORD}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_demo_login_404_when_unseeded(client):
    resp = await client.post("/api/auth/demo-login")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_demo_login_success_when_seeded(client, test_db):
    uid = await _seed_user(test_db, email="demo@x.com", is_demo=True)
    resp = await client.post("/api/auth/demo-login")
    assert resp.status_code == 200
    payload = decode_access_token(resp.json()["access_token"])
    assert payload is not None and payload["user_id"] == str(uid)


@pytest.mark.asyncio
async def test_me_returns_current_user(client, test_db):
    uid = await _seed_user(test_db, email="me@x.com", full_name="Me")
    token = create_access_token({"user_id": str(uid), "email": "me@x.com"})
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(uid)
    assert body["email"] == "me@x.com"
    assert body["full_name"] == "Me"
    assert body["is_demo"] is False


@pytest.mark.asyncio
async def test_me_missing_authorization_header_401(client):
    # HTTPBearer(auto_error=True) rejects a missing header before get_current_user runs.
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_invalid_token_401(client):
    resp = await client.get(
        "/api/auth/me", headers={"Authorization": "Bearer not.a.valid.token"}
    )
    assert resp.status_code == 401
