"""Each visitor's History and downloads belong to their own session: two real sessions A
and B on the demo workspace, one ready-made example, and A's text, card, and document
(with its built files). The real `get_current_user` runs against the test Mongo, so the
scope comes from each token's `sid`. Another visitor's item is a 404 (its existence never
leaks); an example is readable by everyone and read-only for everyone, owners included."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

import app.routes.documents as documents_mod
import app.routes.generate as generate_mod
from app.config import settings
from app.database import get_database
from app.main import app
from app.services import storage_service
from app.services.ai_service import GenerationService
from app.services.session_service import create_session
from app.services.storage_service import build_document_key, get_storage
from app.utils.errors import EXAMPLE_READ_ONLY_COPY
from app.utils.security import create_access_token
from tests.conftest import NS_A, TEST_DB_NAME, build_corpus_chunks
from tests.fakes import FakeGenerationService, FakeVectorStore
from tests.test_ai_routes_budget import (
    CARD_BODY,
    DOC_BODY,
    OWNER_OID,
    POST_BODY,
    TEXT_BODY,
    WS,
    WS_OID,
    _seed_workspace,
)
from tests.test_demo_sessions import _bearer, _seed_user

DEMO_EMAIL = "demo@x.com"
OWNER_EMAIL = "owner@x.com"
OTHER_OWNER_OID = ObjectId()
OTHER_WS_OID = ObjectId()
OTHER_WS = f"/api/workspaces/{OTHER_WS_OID}"


@pytest_asyncio.fixture
async def client(test_db, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    storage_service.get_storage.cache_clear()
    await _seed_user(test_db, email=DEMO_EMAIL, is_demo=True, oid=OWNER_OID)
    await _seed_workspace(test_db)
    store = FakeVectorStore()
    await store.upsert_chunks(NS_A, build_corpus_chunks(NS_A))
    monkeypatch.setattr(generate_mod, "get_vector_store", lambda: store)
    monkeypatch.setattr(documents_mod, "get_vector_store", lambda: store)
    fake_gen = FakeGenerationService()
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[GenerationService] = lambda: fake_gen
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    storage_service.get_storage.cache_clear()


class Visitor:
    def __init__(self, session: dict) -> None:
        self.sid: str = session["_id"]
        self.expires_at: datetime = session["expires_at"]
        token = create_access_token({"user_id": str(OWNER_OID), "email": DEMO_EMAIL, "sid": self.sid})
        self.headers = _bearer(token)


async def _visitor(db) -> Visitor:
    return Visitor(await create_session(db, user_id=OWNER_OID))


async def _seed_generation(
    db, *, type_: str, workspace_oid: ObjectId = WS_OID, visitor: Visitor | None = None,
    is_example: bool = False,
) -> str:
    now = datetime.now(timezone.utc)
    oid = ObjectId()
    if type_ == "card":
        output: dict = {
            "template_id": "photo-led",
            "fields": {"eyebrow": "E", "headline": "Carbon, in the wall", "body": "", "cta": "C",
                       "hashtag": "#H"},
            "image": None,
            "suggested_keywords": ["hemp"],
            "accent_hex": None,
        }
    elif type_ == "document":
        output = {
            "document": {"archetype": "one-pager", "title": "Hempcrete"},
            "formats": {
                fmt: {"storage_key": build_document_key(str(workspace_oid), str(oid), fmt)}
                for fmt in ("docx", "pdf")
            },
        }
        for fmt in ("docx", "pdf"):
            await get_storage().save(build_document_key(str(workspace_oid), str(oid), fmt), b"file")
    else:
        output = {"post_text": "A text post.", "hashtags": [], "char_count": 12}
    doc: dict = {
        "_id": oid,
        "workspace_id": workspace_oid,
        "owner_id": OWNER_OID,
        "type": type_,
        "brief": f"a {type_}",
        "status": "complete",
        "output": output,
        "retrieved_chunk_ids": [],
        "retrieval_meta": [],
        "model": settings.ai_model,
        "embedding_query_model": settings.embedding_model,
        "created_at": now,
        "updated_at": now,
    }
    if is_example:
        doc["is_example"] = True
    if visitor is not None:
        doc["session_id"] = visitor.sid
        doc["expires_at"] = visitor.expires_at
    await db.generations.insert_one(doc)
    return str(oid)


class TwoVisitors:
    a: Visitor
    b: Visitor
    example: str
    a_text: str
    a_card: str
    a_doc: str

    @property
    def a_ids(self) -> set[str]:
        return {self.a_text, self.a_card, self.a_doc}


@pytest_asyncio.fixture
async def two_visitors(client, test_db) -> TwoVisitors:
    v = TwoVisitors()
    v.a = await _visitor(test_db)
    v.b = await _visitor(test_db)
    v.example = await _seed_generation(test_db, type_="card", is_example=True)
    v.a_text = await _seed_generation(test_db, type_="text", visitor=v.a)
    v.a_card = await _seed_generation(test_db, type_="card", visitor=v.a)
    v.a_doc = await _seed_generation(test_db, type_="document", visitor=v.a)
    return v


@pytest_asyncio.fixture
async def owner(client, test_db) -> dict:
    """A signed-in owner (no session) with their own workspace and its own example."""
    await _seed_user(test_db, email=OWNER_EMAIL, is_demo=False, oid=OTHER_OWNER_OID)
    await test_db.workspaces.insert_one(
        {"_id": OTHER_WS_OID, "owner_id": OTHER_OWNER_OID, "name": "Mine", "slug": "mine",
         "brand_profile": {}, "vector_namespace": str(OTHER_WS_OID)}
    )
    example = await _seed_generation(test_db, type_="card", workspace_oid=OTHER_WS_OID, is_example=True)
    token = create_access_token({"user_id": str(OTHER_OWNER_OID), "email": OWNER_EMAIL})
    return {"headers": _bearer(token), "example": example}


def _file_paths(gid: str) -> list[str]:
    return [get_storage().local_path(build_document_key(str(WS_OID), gid, fmt)) for fmt in ("docx", "pdf")]


def _files_exist(gid: str) -> bool:
    return all(os.path.exists(p) for p in _file_paths(gid))


def _files_gone(gid: str) -> bool:
    return not any(os.path.exists(p) for p in _file_paths(gid))


async def test_visitors_see_only_their_own_work_and_the_examples(client, two_visitors):
    v = two_visitors
    a_list = await client.get(f"{WS}/generations", headers=v.a.headers)
    assert a_list.status_code == 200, a_list.text
    assert {i["id"] for i in a_list.json()["items"]} == v.a_ids | {v.example}
    a_count = await client.get(f"{WS}/generations/count", headers=v.a.headers)
    assert a_count.json()["count"] == 4

    b_list = await client.get(f"{WS}/generations", headers=v.b.headers)
    items = b_list.json()["items"]
    assert [i["id"] for i in items] == [v.example]
    assert items[0]["is_example"] is True
    b_count = await client.get(f"{WS}/generations/count", headers=v.b.headers)
    assert b_count.json()["count"] == 1

    # The type filter keeps the scope.
    b_cards = await client.get(f"{WS}/generations", params={"type": "card"}, headers=v.b.headers)
    assert [i["id"] for i in b_cards.json()["items"]] == [v.example]
    b_texts = await client.get(f"{WS}/generations", params={"type": "text"}, headers=v.b.headers)
    assert b_texts.json()["items"] == []

    # The session ID is never returned.
    assert all("session_id" not in i and "expires_at" not in i for i in a_list.json()["items"])


@pytest.mark.parametrize("verb", ["get", "patch", "delete", "download"])
async def test_a_visitor_cannot_reach_another_visitors_generation(client, test_db, two_visitors, verb):
    v = two_visitors
    before = {gid: await test_db.generations.find_one({"_id": ObjectId(gid)}) for gid in v.a_ids}
    for gid in v.a_ids:
        url = f"{WS}/generations/{gid}"
        if verb == "get":
            resp = await client.get(url, headers=v.b.headers)
        elif verb == "patch":
            resp = await client.patch(url, json={"template_id": "quote"}, headers=v.b.headers)
        elif verb == "delete":
            resp = await client.delete(url, headers=v.b.headers)
        else:
            resp = await client.get(f"{url}/download/pdf", headers=v.b.headers)
        assert resp.status_code == 404, (verb, gid, resp.text)
    for gid, doc in before.items():
        assert await test_db.generations.find_one({"_id": ObjectId(gid)}) == doc
    assert _files_exist(v.a_doc)

    # A still reaches all of it.
    for gid in v.a_ids:
        assert (await client.get(f"{WS}/generations/{gid}", headers=v.a.headers)).status_code == 200
    dl = await client.get(f"{WS}/generations/{v.a_doc}/download/pdf", headers=v.a.headers)
    assert dl.status_code == 200
    assert dl.content == b"file"


async def test_examples_are_readable_by_everyone_and_editable_by_no_one(
    client, test_db, two_visitors, owner
):
    v = two_visitors
    cases = [
        (v.a.headers, WS, v.example),
        (v.b.headers, WS, v.example),
        (owner["headers"], OTHER_WS, owner["example"]),
    ]
    for headers, ws, gid in cases:
        url = f"{ws}/generations/{gid}"
        got = await client.get(url, headers=headers)
        assert got.status_code == 200, got.text
        assert got.json()["is_example"] is True
        before = await test_db.generations.find_one({"_id": ObjectId(gid)})
        for resp in (
            await client.patch(url, json={"template_id": "quote"}, headers=headers),
            await client.delete(url, headers=headers),
        ):
            assert resp.status_code == 403, resp.text
            assert resp.json() == {"detail": EXAMPLE_READ_ONLY_COPY, "code": "example_read_only"}
        assert await test_db.generations.find_one({"_id": ObjectId(gid)}) == before


async def test_a_visitor_can_delete_their_own_generation_and_its_files(client, test_db, two_visitors):
    v = two_visitors
    assert _files_exist(v.a_doc)
    resp = await client.delete(f"{WS}/generations/{v.a_doc}", headers=v.a.headers)
    assert resp.status_code == 204, resp.text
    assert await test_db.generations.find_one({"_id": ObjectId(v.a_doc)}) is None
    assert _files_gone(v.a_doc)
    resp = await client.delete(f"{WS}/generations/{v.a_text}", headers=v.a.headers)
    assert resp.status_code == 204
    assert await test_db.generations.count_documents({"session_id": v.a.sid}) == 1


@pytest.mark.parametrize(
    ("route", "body"),
    [("text", TEXT_BODY), ("card", CARD_BODY), ("post", POST_BODY), ("document", DOC_BODY)],
)
async def test_new_generations_carry_the_session_and_its_expiry(client, test_db, route, body):
    a = await _visitor(test_db)
    resp = await client.post(f"{WS}/generate/{route}", json=body, headers=a.headers)
    assert resp.status_code == 200, resp.text
    doc = await test_db.generations.find_one({})
    assert doc is not None
    session = await test_db.demo_sessions.find_one({"_id": a.sid})
    assert doc["session_id"] == a.sid
    assert doc["expires_at"] == session["expires_at"]
    assert "is_example" not in doc or doc["is_example"] is False

    got = await client.get(f"{WS}/generations/{doc['_id']}", headers=a.headers)
    assert got.status_code == 200
    assert got.json()["is_example"] is False
    assert "session_id" not in got.json() and "expires_at" not in got.json()
