"""`_restore_vectors`: an already-seeded workspace gets its corpus vectors back from the
fixture when the vector store is empty (a fresh Chroma directory)."""
import pytest
from bson import ObjectId

from app.config import settings
from seed import seed_demo
from seed.seed_demo import CORPUS, SeedError, _restore_vectors, chunk_key, corpus_chunks
from tests.fakes import FakeVectorStore

NS = "restore-ns"


def _fixture_for(chunks):
    return {chunk_key(c["text"]): [0.5] * settings.embedding_dim for c in chunks}


async def _seeded(test_db):
    ws_id = ObjectId()
    asset_ids = {}
    for filename, _content_type, kind in CORPUS:
        aid = ObjectId()
        asset_ids[filename] = str(aid)
        await test_db.assets.insert_one(
            {"_id": aid, "workspace_id": ws_id, "filename": filename, "asset_kind": kind}
        )
    return {"_id": ws_id, "vector_namespace": NS}, asset_ids


@pytest.fixture
def store(monkeypatch):
    s = FakeVectorStore()
    monkeypatch.setattr(seed_demo, "get_vector_store", lambda: s)
    return s


async def test_empty_store_is_restored_from_the_fixture(test_db, store, monkeypatch):
    workspace, asset_ids = await _seeded(test_db)
    expected = corpus_chunks(NS, asset_ids)
    monkeypatch.setattr(seed_demo, "load_embeddings_fixture", lambda: _fixture_for(expected))
    await _restore_vectors(test_db, workspace)
    assert await store.count(NS) == len(expected)


async def test_non_empty_store_is_left_alone(test_db, store, monkeypatch):
    workspace, _ = await _seeded(test_db)
    await store.upsert_chunks(
        NS, [{"id": "x:0", "text": "t", "metadata": {"asset_kind": "voice"}}], [[0.0]]
    )

    def boom():
        raise AssertionError("fixture must not be loaded")

    monkeypatch.setattr(seed_demo, "load_embeddings_fixture", boom)
    await _restore_vectors(test_db, workspace)
    assert await store.count(NS) == 1


async def test_a_missing_fixture_key_raises_seed_error(test_db, store, monkeypatch):
    workspace, asset_ids = await _seeded(test_db)
    fixture = _fixture_for(corpus_chunks(NS, asset_ids))
    fixture.pop(next(iter(fixture)))
    monkeypatch.setattr(seed_demo, "load_embeddings_fixture", lambda: fixture)
    with pytest.raises(SeedError, match="out of date"):
        await _restore_vectors(test_db, workspace)
