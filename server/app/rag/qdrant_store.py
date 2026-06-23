"""Qdrant (prod) VectorStore — single shared collection, per-workspace payload filter.

Stub for the deferred deployment phase (docs/PLAN.md). Implemented when we flip
`vector_store_backend=qdrant`. Isolation = an indexed payload filter on
`workspace_id` (the only tenant boundary in the shared collection).
"""
from __future__ import annotations

from app.rag.vector_store import Chunk, RetrievedChunk


class QdrantStore:
    def __init__(self) -> None:
        raise NotImplementedError(
            "QdrantStore is implemented in the deployment phase. Use vector_store_backend=chroma for local dev."
        )

    async def upsert_chunks(self, workspace_id: str, chunks: list[Chunk]) -> int: ...
    async def query(self, workspace_id: str, query: str, k: int = 6) -> list[RetrievedChunk]: ...
    async def delete_workspace(self, workspace_id: str) -> None: ...
    async def delete_asset(self, workspace_id: str, asset_id: str) -> None: ...
    async def health(self) -> bool: ...
