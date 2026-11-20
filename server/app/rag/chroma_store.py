"""Chroma VectorStore, in-process: one collection per workspace (`ws_{id}`).

Runs `chromadb.PersistentClient` on a local directory (`settings.chroma_path`); there
is no Chroma server. One process only: two copies must never open the same directory,
so stop the dev API server before running the seed. `PersistentClient`'s own docstring
calls it a development client (chromadb/__init__.py:207-208); that is accepted at this
scale. Chroma's client is sync, so each operation runs in a worker thread.
"""
from __future__ import annotations

import asyncio

from app.config import settings
from app.rag.vector_store import Chunk, RetrievedChunk


class ChromaStore:
    def __init__(self, path: str | None = None) -> None:
        import chromadb

        self._client = chromadb.PersistentClient(
            path=path or settings.chroma_path,
            settings=chromadb.config.Settings(anonymized_telemetry=False, allow_reset=False),
        )
        # The store never embeds: callers pass vectors in, so every embedding call is
        # metered by the caller (see app/rag/embeddings.py).

    def _collection(self, workspace_id: str):
        return self._client.get_or_create_collection(
            name=f"ws_{workspace_id}",
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,  # vectors are always passed in; never load a default model
        )

    async def upsert_chunks(
        self, workspace_id: str, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> int:
        if not chunks:
            return 0

        def _do() -> int:
            col = self._collection(workspace_id)
            col.upsert(
                ids=[c["id"] for c in chunks],
                documents=[c["text"] for c in chunks],
                embeddings=embeddings,
                metadatas=[c["metadata"] for c in chunks],
            )
            return len(chunks)

        return await asyncio.to_thread(_do)

    async def query(
        self, workspace_id: str, query: str, query_embedding: list[float], k: int = 6
    ) -> list[RetrievedChunk]:
        def _do() -> list[RetrievedChunk]:
            col = self._collection(workspace_id)
            res = col.query(
                query_embeddings=[query_embedding],
                n_results=k,
                include=["documents", "metadatas", "distances"],
            )
            ids = (res.get("ids") or [[]])[0]
            docs = (res.get("documents") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            dists = (res.get("distances") or [[]])[0]
            out: list[RetrievedChunk] = []
            for i, _id in enumerate(ids):
                out.append(
                    {
                        "id": _id,
                        "text": docs[i],
                        "score": 1.0 - float(dists[i]),  # cosine distance -> similarity
                        "metadata": metas[i] or {},
                    }
                )
            return out

        return await asyncio.to_thread(_do)

    async def get_by_kinds(
        self, workspace_id: str, kinds: list[str], limit: int = 8
    ) -> list[RetrievedChunk]:
        if not kinds:
            return []

        def _do() -> list[RetrievedChunk]:
            col = self._collection(workspace_id)
            res = col.get(
                where={"asset_kind": {"$in": kinds}},
                limit=limit,
                include=["documents", "metadatas"],
            )
            ids = res.get("ids") or []
            docs = res.get("documents") or []
            metas = res.get("metadatas") or []
            out: list[RetrievedChunk] = []
            for i, _id in enumerate(ids):
                out.append(
                    {
                        "id": _id,
                        "text": docs[i],
                        "score": 1.0,  # pinned: always included, not a similarity hit
                        "metadata": metas[i] or {},
                    }
                )
            return out

        return await asyncio.to_thread(_do)

    async def count(self, workspace_id: str) -> int:
        return await asyncio.to_thread(lambda: self._collection(workspace_id).count())

    async def delete_workspace(self, workspace_id: str) -> None:
        def _do() -> None:
            try:
                self._client.delete_collection(name=f"ws_{workspace_id}")
            except Exception:  # noqa: S110 — best-effort; a missing collection is already gone
                pass

        await asyncio.to_thread(_do)

    async def delete_asset(self, workspace_id: str, asset_id: str) -> None:
        def _do() -> None:
            self._collection(workspace_id).delete(where={"asset_id": asset_id})

        await asyncio.to_thread(_do)

    async def health(self) -> bool:
        def _do() -> bool:
            self._client.heartbeat()  # local call: confirms the in-process client is alive
            return True

        try:
            return await asyncio.to_thread(_do)
        except Exception:
            return False
