"""The public examples API: the four ready-made examples, readable without signing in,
cached for a minute, and their document files downloadable by anyone. Anything that is
not an example document is a 404."""
from __future__ import annotations

import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
from app.main import app
from app.routes import examples as examples_mod
from app.services import storage_service
from app.services.storage_service import build_document_key, get_storage
from seed import seed_demo
from seed.seed_demo import CORPUS, chunk_key, corpus_chunks, ensure_demo_seed
from tests.fakes import FakeVectorStore


@pytest_asyncio.fixture
async def client(test_db, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    storage_service.get_storage.cache_clear()
    examples_mod.clear_examples_cache()
    app.dependency_overrides[get_database] = lambda: test_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    examples_mod.clear_examples_cache()
    storage_service.get_storage.cache_clear()


@pytest_asyncio.fixture
async def seeded(test_db, client, monkeypatch):
    chunks = corpus_chunks("any", {f: "any" for f, _, _ in CORPUS})
    fixture = {chunk_key(c["text"]): [0.25] * settings.embedding_dim for c in chunks}
    monkeypatch.setattr(seed_demo, "load_embeddings_fixture", lambda *a, **k: dict(fixture))
    report = await ensure_demo_seed(test_db, store=FakeVectorStore(), storage=get_storage())
    assert report.ok, report.error
    return {d["example_key"]: d async for d in test_db.generations.find({"is_example": True})}


async def test_examples_are_public_and_cached(client, seeded, test_db):
    res = await client.get("/api/examples")
    assert res.status_code == 200
    assert res.headers["cache-control"] == "public, max-age=60"
    body = res.json()
    assert body["workspace_name"] == "Verdure Materials"
    assert [c["hex"] for c in body["brand"]["colors"]] == ["#1C3A2E", "#F4F1E9", "#C98A3D"]
    assert body["brand"]["fonts"]["heading"] == "DM Serif Display"
    assert set(body["brand"]) == {"colors", "fonts", "accent_hex", "voice_summary"}
    items = body["items"]
    assert len(items) == 4
    assert all(item["is_example"] for item in items)
    assert [item["type"] for item in items] == ["text", "card", "post_pack", "document"]
    assert all("session_id" not in item and "example_key" not in item for item in items)

    # Served from the in-process cache for a minute.
    await test_db.generations.delete_many({"is_example": True})
    again = await client.get("/api/examples")
    assert len(again.json()["items"]) == 4


async def test_an_example_document_downloads_without_signing_in(client, seeded):
    doc_id = str(seeded["document"]["_id"])
    res = await client.get(f"/api/examples/{doc_id}/download/pdf")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content[:4] == b"%PDF"
    docx = await client.get(f"/api/examples/{doc_id}/download/docx")
    assert docx.status_code == 200
    assert docx.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml"
    )


async def test_a_non_example_id_is_404(client, seeded, test_db):
    example = seeded["document"]
    # A visitor's own document in the same workspace, with its file on disk.
    own_id = ObjectId()
    key = build_document_key(str(example["workspace_id"]), str(own_id), "pdf")
    await get_storage().save(key, b"%PDF-1.4 private")
    await test_db.generations.insert_one(
        {
            **{k: v for k, v in example.items() if k not in ("_id", "is_example", "example_key")},
            "_id": own_id,
            "session_id": "someone-else",
            "output": {**example["output"], "formats": {"pdf": {"storage_key": key}}},
        }
    )
    assert (await client.get(f"/api/examples/{own_id}/download/pdf")).status_code == 404
    assert (await client.get(f"/api/examples/{ObjectId()}/download/pdf")).status_code == 404
    assert (await client.get("/api/examples/not-an-id/download/pdf")).status_code == 404
    text_id = str(seeded["text-post"]["_id"])
    assert (await client.get(f"/api/examples/{text_id}/download/pdf")).status_code == 404
    doc_id = str(example["_id"])
    assert (await client.get(f"/api/examples/{doc_id}/download/pptx")).status_code == 404
    assert (await client.get(f"/api/examples/{doc_id}/download/exe")).status_code == 404


async def test_no_seed_means_an_empty_list(client):
    res = await client.get("/api/examples")
    assert res.status_code == 200
    body = res.json()
    assert body["items"] == []
    assert body["workspace_name"] == ""
