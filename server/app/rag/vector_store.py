"""VectorStore protocol + factory.

The implementation is selected by `settings.vector_store_backend`:
- "chroma" (local dev) — one collection per workspace
- "qdrant" (prod)      — one shared collection, isolation via payload filter

Both pin 1536-dim / cosine and store identical payloads, so switching backends
is a config flip. See docs/ARCHITECTURE.md §3.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Protocol, TypedDict, runtime_checkable

from app.config import settings


class Chunk(TypedDict):
    id: str  # "{asset_id}:{chunk_index}"
    text: str
    metadata: dict  # {workspace_id, asset_id, filename, asset_kind, chunk_index, page?}


class RetrievedChunk(TypedDict):
    id: str
    text: str
    score: float
    metadata: dict


@runtime_checkable
class VectorStore(Protocol):
    async def upsert_chunks(self, workspace_id: str, chunks: list[Chunk]) -> int: ...
    async def query(self, workspace_id: str, query: str, k: int = 6) -> list[RetrievedChunk]: ...
    async def delete_workspace(self, workspace_id: str) -> None: ...
    async def delete_asset(self, workspace_id: str, asset_id: str) -> None: ...
    async def health(self) -> bool: ...


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    backend = settings.vector_store_backend
    if backend == "chroma":
        from app.rag.chroma_store import ChromaStore

        return ChromaStore()
    if backend == "qdrant":
        from app.rag.qdrant_store import QdrantStore

        return QdrantStore()
    raise ValueError(f"Unknown vector_store_backend: {backend!r} (expected 'chroma' or 'qdrant')")
