"""Phase 6 PR-B — ingestion is bounded: a slow parse times out and an oversized
doc is rejected, both marking the asset `error` with nothing upserted."""
import time

import pytest
from bson import ObjectId

import app.services.ingestion_service as ing
from app.models.common import utcnow
from app.rag.loaders import Section
from tests.fakes import FakeVectorStore

NS = "ws-ns"


class _FakeStorage:
    def local_path(self, key: str) -> str:
        return "/tmp/unused"


async def _seed_asset(db) -> str:
    oid = ObjectId()
    now = utcnow()
    await db.assets.insert_one({
        "_id": oid, "workspace_id": ObjectId(), "filename": "big.md",
        "content_type": "text/markdown", "asset_kind": "other", "storage_key": "k",
        "size_bytes": 1, "ingestion_status": "processing", "chunk_count": 0,
        "error": None, "ingested_at": None, "created_at": now, "updated_at": now,
    })
    return str(oid)


@pytest.mark.asyncio
async def test_chunk_cap_rejects_oversized(test_db, monkeypatch):
    store = FakeVectorStore()

    async def _db():
        return test_db

    monkeypatch.setattr(ing, "get_database", _db)
    monkeypatch.setattr(ing, "get_storage", lambda: _FakeStorage())
    monkeypatch.setattr(ing, "get_vector_store", lambda: store)
    monkeypatch.setattr(ing, "load_sections", lambda path, ct: [Section(text="x", page=None)])
    monkeypatch.setattr(ing, "MAX_CHUNKS", 3)
    monkeypatch.setattr(ing, "build_chunks", lambda **kw: [{"id": f"a:{i}", "text": "t", "metadata": {}} for i in range(5)])

    asset_id = await _seed_asset(test_db)
    await ing.ingest_asset(asset_id, NS)

    doc = await test_db.assets.find_one({"_id": ObjectId(asset_id)})
    assert doc["ingestion_status"] == "error"
    assert "too large" in doc["error"].lower()
    assert await store.query(NS, "t") == []  # nothing upserted


@pytest.mark.asyncio
async def test_parse_timeout_marks_error(test_db, monkeypatch):
    async def _db():
        return test_db

    def _slow(path, ct):
        time.sleep(0.3)
        return []

    monkeypatch.setattr(ing, "get_database", _db)
    monkeypatch.setattr(ing, "get_storage", lambda: _FakeStorage())
    monkeypatch.setattr(ing, "get_vector_store", lambda: FakeVectorStore())
    monkeypatch.setattr(ing, "load_sections", _slow)
    monkeypatch.setattr(ing, "PARSE_TIMEOUT_S", 0.05)

    asset_id = await _seed_asset(test_db)
    await ing.ingest_asset(asset_id, NS)

    doc = await test_db.assets.find_one({"_id": ObjectId(asset_id)})
    assert doc["ingestion_status"] == "error"
    assert "timed out" in doc["error"].lower()
