"""Metering around a model call: reserve first, settle from real usage, never leak a line.

`reserve_action` takes a reservation per planned model call. Each `MeteredLine` settles once
(later settles are no-ops). `MeteredAction.finalize` runs on exit, even when canceled: a line
that started but never settled keeps its full reservation (`canceled_or_unknown`), and one
that never started is released at 0 (`not_attempted`).
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from types import TracebackType
from typing import Any

import anyio
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import settings
from app.services.ai_ledger import LineRequest, ReservedLine, reserve, settle
from app.services.ai_pricing import (
    IMAGE_TOKEN_BOUND,
    SCHEMA_OVERHEAD_TOKENS,
    claude_cost_micros,
    claude_reservation_micros,
    embedding_cost_micros,
    embedding_reservation_micros,
    estimate_tokens,
)


class MeteredLine:
    def __init__(self, db: AsyncIOMotorDatabase, reserved: ReservedLine) -> None:
        self._db = db
        self.reserved = reserved
        self.started = False
        self.settled = False

    def mark_started(self) -> None:
        """Call just before the request goes out: from here an unknown outcome is billed."""
        self.started = True

    async def _close(self, actual_micros: int, outcome: str) -> None:
        if self.settled:
            return
        self.settled = True
        await settle(self._db, self.reserved, actual_micros=actual_micros, outcome=outcome)

    async def settle_usage(
        self,
        *,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> None:
        cost = claude_cost_micros(
            model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
        )
        await self._close(cost, "ok")

    async def settle_tokens(self, tokens: int) -> None:
        """Embeddings: settle from the token count the API reported."""
        await self._close(embedding_cost_micros(self.reserved.model, tokens), "ok")

    async def settle_unbilled(self, outcome: str) -> None:
        await self._close(0, outcome)

    async def settle_reserved(self, outcome: str) -> None:
        await self._close(self.reserved.reserved_micros, outcome)


class MeteredAction:
    def __init__(self, lines: list[MeteredLine]) -> None:
        self.lines = lines

    async def finalize(self) -> None:
        with anyio.CancelScope(shield=True):
            for line in self.lines:
                if line.settled:
                    continue
                if line.started:
                    await line.settle_reserved("canceled_or_unknown")
                else:
                    await line.settle_unbilled("not_attempted")

    async def __aenter__(self) -> MeteredAction:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.finalize()


async def reserve_action(
    db: AsyncIOMotorDatabase, requests: Sequence[LineRequest], *, visitor_id: str | None
) -> MeteredAction:
    reserved = await reserve(db, requests, visitor_id=visitor_id)
    return MeteredAction([MeteredLine(db, r) for r in reserved])


def claude_line(
    purpose: str,
    *,
    system: str,
    content: str | list[dict[str, Any]],
    max_tokens: int,
    schema: dict[str, Any] | None = None,
    extra_input_tokens: int = 0,
) -> LineRequest:
    tokens = estimate_tokens(system) + extra_input_tokens
    if isinstance(content, str):
        tokens += estimate_tokens(content)
    else:
        for part in content:
            if part.get("type") == "image":
                tokens += IMAGE_TOKEN_BOUND
            elif isinstance(part.get("text"), str):
                tokens += estimate_tokens(part["text"])
    if schema is not None:
        tokens += estimate_tokens(json.dumps(schema)) + SCHEMA_OVERHEAD_TOKENS
    model = settings.ai_model
    return LineRequest(
        "anthropic", model, purpose, claude_reservation_micros(model, input_tokens=tokens, max_tokens=max_tokens)
    )


def embedding_line(purpose: str, texts: Sequence[str]) -> LineRequest:
    model = settings.embedding_model
    return LineRequest("openai", model, purpose, embedding_reservation_micros(model, texts))
