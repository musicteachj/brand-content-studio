"""The one place that shapes a Claude request (DECISIONS #40).

Every model call in the app is one of two kinds, and both services
(`ai_service`, `brand_extract_service`) go through here so the request shape
can't drift between them:

- `stream_text`: streamed prose for the live typing effect. Only text deltas are
  yielded; thinking blocks never reach the client.
- `structured_call`: one request whose reply is JSON matching a strict schema
  (structured outputs, `output_config.format`). Claude Sonnet 5.5 rejects a
  forced `tool_choice`, which is how this used to be done; the existing strict
  tool definitions are reused for their schema.

Shared request options: the model and effort come from settings. There is no
server-side fallback: a policy decline raises `ModelDeclined`, which the SSE
wrapper and an app exception handler turn into a readable message instead of the
generic redacted error. A streamed call carries its own read timeout."""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any, cast

from anthropic import AsyncAnthropic
from anthropic.types.beta import BetaMessageParam

from app.config import settings
from app.services.ai_clients import stream_timeout
from app.utils.errors import UserFacingError

logger = logging.getLogger(__name__)

DECLINED_MESSAGE = "The model declined this request. Try rewording the brief."


class ModelDeclined(UserFacingError):
    """The model (and any fallback) declined the request: `stop_reason == "refusal"`."""

    def __init__(self, category: str | None = None) -> None:
        super().__init__(
            DECLINED_MESSAGE, log_detail=f"Model declined the request (category: {category})"
        )
        self.category = category


def request_options() -> dict[str, Any]:
    """Options every request shares. `output_config` is rebuilt per call (the
    structured call adds a `format` to it), so callers get a fresh dict."""
    return {
        "model": settings.ai_model,
        "output_config": {"effort": settings.ai_effort},
    }


def _raise_if_declined(message: Any) -> None:
    # Branch on stop_reason, never on stop_details (which can be null on a refusal).
    if message.stop_reason == "refusal":
        details = getattr(message, "stop_details", None)
        category = getattr(details, "category", None) if details is not None else None
        logger.warning("Model declined a request (category: %s)", category)
        raise ModelDeclined(category)


async def stream_text(
    client: AsyncAnthropic, *, system: str, user: str, max_tokens: int
) -> AsyncGenerator[str, None]:
    """Stream prose, yielding text deltas only. A decline or a hit token cap is
    checked once the stream ends: text already sent stays on screen and the
    route's error frame follows it, so nothing is persisted."""
    async with client.beta.messages.stream(  # type: ignore[call-overload]
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        timeout=stream_timeout(),
        **request_options(),
    ) as stream:
        async for text in stream.text_stream:
            yield text
        final = await stream.get_final_message()
    _raise_if_declined(final)
    if final.stop_reason == "max_tokens":
        # Thinking counts toward the cap; cut-off prose must not be saved as done.
        raise RuntimeError(f"Streamed output hit the {max_tokens}-token cap.")


async def structured_call(
    client: AsyncAnthropic,
    *,
    system: str,
    content: str | list[dict[str, Any]],
    tool: dict[str, Any],
    max_tokens: int,
) -> dict[str, Any]:
    """One request whose reply is JSON matching `tool["input_schema"]`. The tool's
    one-line description is kept as an instruction at the end of the system prompt,
    since there is no tool to carry it any more."""
    options = request_options()
    options["output_config"]["format"] = {"type": "json_schema", "schema": tool["input_schema"]}
    message = await client.beta.messages.create(  # type: ignore[call-overload]
        max_tokens=max_tokens,
        system=f"{system}\n\nRespond with JSON only. {tool['description']}",
        messages=cast("list[BetaMessageParam]", [{"role": "user", "content": content}]),
        **options,
    )
    _raise_if_declined(message)
    if message.stop_reason == "max_tokens":
        raise RuntimeError(f"{tool['name']} output hit the {max_tokens}-token cap.")
    # Read by type: with adaptive thinking a response can open with a thinking block.
    for block in message.content:
        if block.type == "text":
            return dict(json.loads(block.text))
    raise RuntimeError(f"Model returned no JSON for {tool['name']}.")
