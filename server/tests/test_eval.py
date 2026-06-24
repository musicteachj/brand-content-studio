"""RAG eval harness — a small brief→expected-chunk fixture set gives retrieval
quality a *number* we can tune chunking / k / weighting against, instead of a
vibe (PLAN Phase 1a). With the lexical fake store this exercises the harness
mechanism; against real embeddings the same fixtures measure semantic recall.
"""
import pytest

from app.services import retrieval_service
from tests.conftest import NS_A

# brief -> the past-post chunk id we expect retrieval to surface.
EVAL_SET = {
    "hempcrete carbon sequestration per cubic meter": "posts-asset:0",
    "reclaimed oak beam cladding carbon debt": "posts-asset:1",
    "a sustainable claim needs a number metric attached": "posts-asset:2",
    "mycelium acoustic panels studio reverberation": "posts-asset:3",
    "embodied carbon operational emissions before handover": "posts-asset:5",
    "will bio-based materials last durability service life for contractors": "posts-asset:6",
    "we turned down a greenwash veneer project": "posts-asset:7",
    "Larkfield mixed-use block envelope cut embodied carbon 38%": "posts-asset:10",
}

HIT_RATE_THRESHOLD = 0.75


@pytest.mark.asyncio
async def test_retrieval_hit_rate_meets_threshold(ingested_store):
    hits = 0
    misses: list[str] = []
    for brief, expected_id in EVAL_SET.items():
        result = await retrieval_service.retrieve(ingested_store, NS_A, brief, k=6)
        if expected_id in result.chunk_ids:
            hits += 1
        else:
            misses.append(f"{brief!r} -> {expected_id}")

    hit_rate = hits / len(EVAL_SET)
    assert hit_rate >= HIT_RATE_THRESHOLD, (
        f"retrieval hit-rate {hit_rate:.2f} below {HIT_RATE_THRESHOLD}; misses: {misses}"
    )
