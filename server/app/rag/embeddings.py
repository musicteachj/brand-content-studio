"""Embedder protocol + OpenAI implementation, and the metered way to call it.

All embedding goes through this so the provider swaps in one place
(docs/DECISIONS.md #6). `embed_with_usage` is sync (callers use `embed_metered`, which
runs it in a thread and settles the ledger line from the reported token count). Vector
stores never embed; callers pass vectors in.
"""
from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Protocol

import openai

from app.config import settings
from app.services.ai_meter import MeteredLine
from app.utils.errors import LiveAIUnavailable

logger = logging.getLogger(__name__)

# OpenAI rejected the request before doing any work: nothing was billed.
_UNBILLED_ERRORS = (
    openai.AuthenticationError,
    openai.PermissionDeniedError,
    openai.BadRequestError,
    openai.RateLimitError,  # includes insufficient_quota and credit_balance_exhausted
)


class Embedder(Protocol):
    def embed_with_usage(self, texts: list[str]) -> tuple[list[list[float]], int]:
        """Vectors in input order, and the response's `usage.total_tokens`."""
        ...


class OpenAIEmbedder:
    def __init__(self) -> None:
        from app.services.ai_clients import get_openai

        self._client = get_openai()
        self._model = settings.embedding_model

    def embed_with_usage(self, texts: list[str]) -> tuple[list[list[float]], int]:
        if not texts:
            return [], 0
        resp = self._client.embeddings.create(model=self._model, input=texts)
        usage = getattr(resp, "usage", None)
        tokens = int(getattr(usage, "total_tokens", 0) or 0)
        return [d.embedding for d in resp.data], tokens


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    return OpenAIEmbedder()


async def embed_metered(texts: list[str], *, line: MeteredLine) -> list[list[float]]:
    """Embed `texts` against a reserved ledger line and settle it from the reported tokens.

    A rejected request (auth, permission, bad request, any 429) settles to $0; a timeout,
    dropped connection, or unknown outcome keeps the reservation (the caller's action
    settles it). Any OpenAI error reaches the visitor as `LiveAIUnavailable`."""
    if not texts:
        await line.settle_unbilled("not_attempted")
        return []
    try:
        embedder = get_embedder()
    except openai.OpenAIError as exc:
        # No usable key: the SDK refuses to build a client, so no request was made.
        await line.settle_unbilled("client_unavailable")
        logger.warning("Embedding client unavailable: %s", type(exc).__name__)
        raise LiveAIUnavailable(
            log_detail=f"Embedding client unavailable: {type(exc).__name__}"
        ) from exc
    line.mark_started()
    try:
        vectors, tokens = await asyncio.to_thread(embedder.embed_with_usage, texts)
    except openai.APIError as exc:
        if isinstance(exc, _UNBILLED_ERRORS):
            await line.settle_unbilled(type(exc).__name__)
        logger.warning("Embedding call failed: %s", type(exc).__name__)
        raise LiveAIUnavailable(log_detail=f"Embedding call failed: {type(exc).__name__}") from exc
    await line.settle_tokens(tokens)
    return vectors
