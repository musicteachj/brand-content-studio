"""VectorStore protocol + factory.

The one implementation is Chroma, in-process on local disk
(`settings.vector_store_backend == "chroma"`): one collection per workspace, 1536-dim /
cosine. See docs/ARCHITECTURE.md §3.
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
    async def upsert_chunks(
        self, workspace_id: str, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> int:
        """Store `chunks` with their precomputed vectors (stores never embed)."""
        ...

    async def query(
        self, workspace_id: str, query: str, query_embedding: list[float], k: int = 6
    ) -> list[RetrievedChunk]:
        """Nearest chunks to `query_embedding`. `query` is the text it came from."""
        ...

    async def get_by_kinds(
        self, workspace_id: str, kinds: list[str], limit: int = 8
    ) -> list[RetrievedChunk]:
        """Fetch chunks by `asset_kind`, regardless of similarity. Used for the
        always-injected brand fundamentals (voice/pillars) in hybrid retrieval."""
        ...

    async def count(self, workspace_id: str) -> int:
        """Number of chunks stored for the workspace."""
        ...

    async def delete_workspace(self, workspace_id: str) -> None: ...
    async def delete_asset(self, workspace_id: str, asset_id: str) -> None: ...
    async def health(self) -> bool: ...


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    backend = settings.vector_store_backend
    if backend == "chroma":
        from app.rag.chroma_store import ChromaStore

        return ChromaStore()
    raise ValueError(f"Unknown vector_store_backend: {backend!r} (expected 'chroma')")
