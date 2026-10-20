"""Embedder protocol + OpenAI implementation.

All embedding goes through this so the provider swaps in one place
(docs/DECISIONS.md #6). Calls are sync; callers wrap them in a thread.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from app.config import settings


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class OpenAIEmbedder:
    def __init__(self) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=settings.openai_api_key.get_secret_value())
        self._model = settings.embedding_model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = self._client.embeddings.create(model=self._model, input=texts)
        return [d.embedding for d in resp.data]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    return OpenAIEmbedder()
