"""Integration: the ingestion BackgroundTask flips the asset to ready, records a
chunk count, and bumps the workspace's retrievable-chunk counter."""
import pytest
from bson import ObjectId

import app.database as database_mod
import app.services.ingestion_service as ingestion_mod
from app.config import settings
from app.services.ingestion_service import ingest_asset
from app.services.storage_service import build_storage_key, get_storage
from tests.conftest import TEST_DB_NAME
from tests.fakes import FakeVectorStore

SAMPLE_MD = (
    "# Brand Voice\n\n"
    "Verdure is grounded and data-first. We lead with the number, then the meaning. "
    "We respect the reader's intelligence and never greenwash.\n\n"
    "We talk in embodied carbon, life-cycle assessment, and tested performance."
)


@pytest.mark.asyncio
async def test_ingestion_marks_ready_and_counts_chunks(test_db, tmp_path, monkeypatch):
    # Point the app at the test DB, a tmp storage dir, and a fake vector store.
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    monkeypatch.setattr(database_mod.db, "client", test_db.client)
    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    get_storage.cache_clear()
    fake_store = FakeVectorStore()
    monkeypatch.setattr(ingestion_mod, "get_vector_store", lambda: fake_store)

    workspace_oid = ObjectId()
    namespace = str(workspace_oid)
    await test_db.workspaces.insert_one(
        {"_id": workspace_oid, "vector_namespace": namespace, "ready_chunk_count": 0}
    )

    asset_oid = ObjectId()
    storage_key = build_storage_key(namespace, str(asset_oid), "voice.md")
    await get_storage().save(storage_key, SAMPLE_MD.encode("utf-8"))
    await test_db.assets.insert_one(
        {
            "_id": asset_oid,
            "workspace_id": workspace_oid,
            "filename": "voice.md",
            "content_type": "text/markdown",
            "asset_kind": "voice",
            "storage_key": storage_key,
            "ingestion_status": "processing",
            "chunk_count": 0,
        }
    )

    await ingest_asset(str(asset_oid), namespace)

    asset = await test_db.assets.find_one({"_id": asset_oid})
    assert asset["ingestion_status"] == "ready"
    assert asset["chunk_count"] > 0
    assert asset["ingested_at"] is not None

    workspace = await test_db.workspaces.find_one({"_id": workspace_oid})
    assert workspace["ready_chunk_count"] == asset["chunk_count"]

    # The chunks actually landed in the (fake) vector store, scoped to the namespace.
    hits = await fake_store.query(namespace, "embodied carbon", k=5)
    assert hits and all(h["metadata"]["asset_id"] == str(asset_oid) for h in hits)
    get_storage.cache_clear()
