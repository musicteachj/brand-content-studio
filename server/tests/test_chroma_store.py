"""The real in-process ChromaStore on a temp directory, with tiny vectors."""
from app.rag.chroma_store import ChromaStore


def _chunk(cid: str, asset: str, kind: str, text: str) -> dict:
    return {
        "id": cid,
        "text": text,
        "metadata": {"workspace_id": "w", "asset_id": asset, "asset_kind": kind, "chunk_index": 0},
    }


async def _fill(store: ChromaStore) -> None:
    await store.upsert_chunks(
        "w",
        [
            _chunk("a:0", "a", "voice", "x axis"),
            _chunk("a:1", "a", "voice", "y axis"),
            _chunk("b:0", "b", "posts", "z axis"),
        ],
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
    )


async def test_upsert_query_count_and_delete_round_trip(tmp_path):
    store = ChromaStore(path=str(tmp_path))
    await _fill(store)
    assert await store.count("w") == 3
    hits = await store.query("w", "x", [0.9, 0.1, 0.0], k=2)
    assert [h["id"] for h in hits] == ["a:0", "a:1"]
    assert hits[0]["score"] > hits[1]["score"]
    await store.delete_asset("w", "a")
    assert await store.count("w") == 1
    await store.delete_workspace("w")
    assert await store.count("w") == 0


async def test_get_by_kinds_returns_pinned_chunks(tmp_path):
    store = ChromaStore(path=str(tmp_path))
    await _fill(store)
    pinned = await store.get_by_kinds("w", ["posts"])
    assert [p["id"] for p in pinned] == ["b:0"]
    assert pinned[0]["score"] == 1.0
    assert await store.get_by_kinds("w", []) == []


async def test_health_is_true_for_a_local_store(tmp_path):
    assert await ChromaStore(path=str(tmp_path)).health() is True


def test_telemetry_is_off(tmp_path):
    assert ChromaStore(path=str(tmp_path))._client.get_settings().anonymized_telemetry is False


async def test_chroma_never_loads_its_default_embedding_model(tmp_path, monkeypatch):
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    def boom(*args, **kwargs):
        raise AssertionError("Chroma tried to load its default embedding model")

    monkeypatch.setattr(DefaultEmbeddingFunction, "__init__", boom)
    store = ChromaStore(path=str(tmp_path))
    await _fill(store)
    assert len(await store.query("w", "x", [1.0, 0.0, 0.0], k=1)) == 1
    await store.delete_workspace("w")


async def test_empty_upsert_is_a_no_op(tmp_path):
    assert await ChromaStore(path=str(tmp_path)).upsert_chunks("w", [], []) == 0
