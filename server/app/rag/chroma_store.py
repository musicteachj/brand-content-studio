"""Chroma (local dev) VectorStore — one collection per workspace (`ws_{id}`).

Connects to the chromadb/chroma container from docker-compose via HttpClient.
Chroma's client is sync, so each operation runs in a worker thread.
"""
from __future__ import annotations

import asyncio

from app.config import settings
from app.rag.embeddings import get_embedder
from app.rag.vector_store import Chunk, RetrievedChunk


class ChromaStore:
    def __init__(self) -> None:
        import chromadb

        self._client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
        # Embedder is built lazily (get_embedder is cached) so booting / health
        # checks don't require an OpenAI key — only ingest/query do.

    def _collection(self, workspace_id: str):
        return self._client.get_or_create_collection(
            name=f"ws_{workspace_id}",
            metadata={"hnsw:space": "cosine"},
        )

    async def upsert_chunks(self, workspace_id: str, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0

        def _do() -> int:
            col = self._collection(workspace_id)
            embeddings = get_embedder().embed_documents([c["text"] for c in chunks])
            col.upsert(
                ids=[c["id"] for c in chunks],
                documents=[c["text"] for c in chunks],
                embeddings=embeddings,
                metadatas=[c["metadata"] for c in chunks],
            )
            return len(chunks)

        return await asyncio.to_thread(_do)

    async def query(self, workspace_id: str, query: str, k: int = 6) -> list[RetrievedChunk]:
        def _do() -> list[RetrievedChunk]:
            col = self._collection(workspace_id)
            qvec = get_embedder().embed_query(query)
            res = col.query(
                query_embeddings=[qvec],
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

    async def delete_workspace(self, workspace_id: str) -> None:
        def _do() -> None:
            try:
                self._client.delete_collection(name=f"ws_{workspace_id}")
            except Exception:
                pass

        await asyncio.to_thread(_do)

    async def delete_asset(self, workspace_id: str, asset_id: str) -> None:
        def _do() -> None:
            self._collection(workspace_id).delete(where={"asset_id": asset_id})

        await asyncio.to_thread(_do)

    async def health(self) -> bool:
        def _do() -> bool:
            self._client.heartbeat()
            return True

        try:
            return await asyncio.to_thread(_do)
        except Exception:
            return False
