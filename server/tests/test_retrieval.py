"""Retrieval: workspace-scoped, top-k with scores, hybrid always-includes-voice."""
import pytest

from app.services import retrieval_service
from tests.conftest import NS_A, NS_B, build_corpus_chunks


@pytest.mark.asyncio
async def test_query_is_workspace_scoped(fake_store):
    # Ingest distinct corpora into two workspaces; query one, assert no cross-leak.
    await fake_store.upsert_chunks(NS_A, build_corpus_chunks(NS_A))
    await fake_store.upsert_chunks(NS_B, build_corpus_chunks(NS_B))

    result = await retrieval_service.retrieve(fake_store, NS_A, "hempcrete embodied carbon", k=6)

    assert result.chunks, "expected hits in workspace A"
    for chunk in result.chunks:
        assert chunk["metadata"]["workspace_id"] == NS_A
        assert not chunk["id"].startswith(NS_B)


@pytest.mark.asyncio
async def test_retrieval_returns_topk_with_scores(ingested_store):
    result = await retrieval_service.retrieve(
        ingested_store, NS_A, "mycelium acoustic panels", k=4
    )
    semantic = [c for c in result.chunks if c["id"] not in {m["chunk_id"] for m in result.meta if m["pinned"]}]
    assert len(semantic) <= 4
    assert all(isinstance(c["score"], float) for c in result.chunks)
    # Every chunk has a debug-panel meta item with a preview.
    assert len(result.meta) == len(result.chunks)
    assert all(m["preview"] for m in result.meta)
    assert result.envelope()["embedding_model"]


@pytest.mark.asyncio
async def test_hybrid_retrieval_always_includes_voice_and_pillars(ingested_store):
    # A brief with no lexical overlap must still pull BOTH voice and pillars —
    # neither pinned kind may crowd the other out (DECISIONS #16).
    result = await retrieval_service.retrieve(
        ingested_store, NS_A, "zzz unrelated gibberish qqq", k=6
    )
    kinds = {c["metadata"]["asset_kind"] for c in result.chunks}
    assert "voice" in kinds, "voice fundamentals must always be injected"
    assert "pillars" in kinds, "pillar fundamentals must always be injected"
    assert any(m["pinned"] for m in result.meta)


@pytest.mark.asyncio
async def test_different_briefs_retrieve_different_chunks(ingested_store):
    a = await retrieval_service.retrieve(ingested_store, NS_A, "hempcrete carbon sequestration", k=6)
    b = await retrieval_service.retrieve(ingested_store, NS_A, "reclaimed timber cladding supply", k=6)
    # Pinned fundamentals overlap, but the semantic hits should differ.
    a_semantic = {m["chunk_id"] for m in a.meta if not m["pinned"]}
    b_semantic = {m["chunk_id"] for m in b.meta if not m["pinned"]}
    assert a_semantic != b_semantic, "distinct briefs should retrieve distinct exemplars"
