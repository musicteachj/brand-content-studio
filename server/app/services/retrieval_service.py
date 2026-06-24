"""Hybrid, workspace-scoped retrieval.

The brand fundamentals (voice + pillars) are *always* injected so they don't
depend on a similarity hit (DECISIONS #16); semantic top-k then adds the most
relevant exemplar posts/sections. Every call is scoped to one workspace's
namespace — the only tenant boundary (ARCHITECTURE gotcha #7)."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from app.config import settings
from app.rag.vector_store import RetrievedChunk, VectorStore

PINNED_KINDS = ["voice", "pillars"]
# Voice + pillars are small, curated docs that must *both* always be injected
# (DECISIONS #16). Use a limit comfortably above their combined chunk count so
# one kind (e.g. a multi-chunk voice guide) can't crowd the other out.
PINNED_LIMIT = 16
PREVIEW_CHARS = 240


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]  # merged, ordered (pinned first), deduped
    meta: list[dict] = field(default_factory=list)  # debug-panel snapshot per chunk
    latency_ms: int = 0
    embedding_model: str = settings.embedding_model
    k: int = 6

    def envelope(self) -> dict:
        """Terminal SSE `meta` payload (ARCHITECTURE §5 debug-panel contract)."""
        return {
            "k": self.k,
            "retrieved": self.meta,
            "embedding_model": self.embedding_model,
            "latency_ms": self.latency_ms,
        }

    @property
    def chunk_ids(self) -> list[str]:
        return [c["id"] for c in self.chunks]


def _meta_item(chunk: RetrievedChunk, pinned: bool) -> dict:
    meta = chunk.get("metadata") or {}
    text = chunk.get("text") or ""
    return {
        "chunk_id": chunk["id"],
        "asset_id": meta.get("asset_id", ""),
        "filename": meta.get("filename", "unknown"),
        "asset_kind": meta.get("asset_kind", "other"),
        "score": round(float(chunk.get("score", 0.0)), 4),
        "preview": text[:PREVIEW_CHARS],
        "chunk_index": int(meta.get("chunk_index", 0)),
        "page": meta.get("page"),
        "pinned": pinned,
    }


async def retrieve(store: VectorStore, namespace: str, query: str, k: int = 6) -> RetrievalResult:
    start = time.perf_counter()

    # The pinned fetch and the semantic query are independent — overlap them so
    # the embedding round-trip doesn't add to time-to-first-token.
    fundamentals, semantic = await asyncio.gather(
        store.get_by_kinds(namespace, PINNED_KINDS, limit=PINNED_LIMIT),
        store.query(namespace, query, k=k),
    )

    # Pinned fundamentals first, in the store's order (deterministic — not set
    # iteration), then semantic hits by descending score, deduped.
    pinned_ids = {c["id"] for c in fundamentals}
    ordered: list[RetrievedChunk] = list(fundamentals)
    seen = set(pinned_ids)
    for chunk in sorted(semantic, key=lambda c: c.get("score", 0.0), reverse=True):
        if chunk["id"] not in seen:
            seen.add(chunk["id"])
            ordered.append(chunk)

    latency_ms = int((time.perf_counter() - start) * 1000)
    meta = [_meta_item(c, pinned=c["id"] in pinned_ids) for c in ordered]
    return RetrievalResult(
        chunks=ordered,
        meta=meta,
        latency_ms=latency_ms,
        embedding_model=settings.embedding_model,
        k=k,
    )
