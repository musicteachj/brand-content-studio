"""The one place that shapes a Claude request (DECISIONS #40), and meters it.

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
generic redacted error. A streamed call carries its own read timeout and a deadline
for the whole stream.

Metering: each call takes the `MeteredLine` its route reserved, and settles it exactly
once. A response is billed, so its usage is settled before a decline, a token cap, or bad
JSON is raised. A failure the provider never billed (`ai_failures`) settles to $0. A timeout,
dropped connection, cancellation, or unknown outcome keeps the whole reservation. A provider
outage is raised as `LiveAIUnavailable` (friendly copy); any other API error is re-raised."""
from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any, cast

import anthropic
import anyio
import httpx
from anthropic import AsyncAnthropic
from anthropic.types.beta import BetaMessageParam

from app.config import settings
from app.services.ai_clients import stream_timeout
from app.services.ai_failures import Billing, classify_anthropic_error, is_provider_outage
from app.services.ai_ledger import LineRequest
from app.services.ai_meter import MeteredLine, claude_line
from app.services.ai_pricing import claude_cost_micros
from app.utils.errors import LiveAIUnavailable, UserFacingError

logger = logging.getLogger(__name__)

DECLINED_MESSAGE = "The model declined this request. Try rewording the brief."
# How long closing a stream may take when the caller is canceled.
_CLOSE_TIMEOUT_S = 5
_UNSETTLED = "canceled_or_unknown"
# Stream events that carry content (text or thinking), as opposed to message bookkeeping.
_CONTENT_EVENTS = frozenset({"content_block_start", "content_block_delta"})
# What a failed call can raise: the SDK's errors, and httpx's for a stream that breaks
# while its body is being read (the SDK doesn't wrap those).
_CALL_ERRORS = (anthropic.APIError, httpx.TransportError)


class ModelDeclined(UserFacingError):
    """The model (and any fallback) declined the request: `stop_reason == "refusal"`."""

    def __init__(self, category: str | None = None) -> None:
        super().__init__(
            DECLINED_MESSAGE, log_detail=f"Model declined the request (category: {category})"
        )
        self.category = category


class StreamDeadlineExceeded(Exception):
    """A stream ran past `settings.ai_stream_deadline_s`."""


def request_options() -> dict[str, Any]:
    """Options every request shares. `output_config` is rebuilt per call (the
    structured call adds a `format` to it), so callers get a fresh dict."""
    return {
        "model": settings.ai_model,
        "output_config": {"effort": settings.ai_effort},
    }


def structured_system(system: str, tool: dict[str, Any]) -> str:
    """The system prompt a structured call sends: the tool's one-line description is
    kept as an instruction at the end, since there is no tool to carry it any more."""
    return f"{system}\n\nRespond with JSON only. {tool['description']}"


def text_line(purpose: str, *, system: str, user: str, max_tokens: int) -> LineRequest:
    """The reservation for one `stream_text` call."""
    return claude_line(purpose, system=system, content=user, max_tokens=max_tokens)


def structured_line(
    purpose: str,
    *,
    system: str,
    content: str | list[dict[str, Any]],
    tool: dict[str, Any],
    max_tokens: int,
    extra_input_tokens: int = 0,
) -> LineRequest:
    """The reservation for one `structured_call`, counting the system prompt as sent and
    the schema. `extra_input_tokens` holds room for text not written yet (the second call
    of a two-call action carries the first call's output)."""
    return claude_line(
        purpose,
        system=structured_system(system, tool),
        content=content,
        max_tokens=max_tokens,
        schema=tool["input_schema"],
        extra_input_tokens=extra_input_tokens,
    )


def _raise_if_declined(message: Any) -> None:
    # Branch on stop_reason, never on stop_details (which can be null on a refusal).
    if message.stop_reason == "refusal":
        details = getattr(message, "stop_details", None)
        category = getattr(details, "category", None) if details is not None else None
        logger.warning("Model declined a request (category: %s)", category)
        raise ModelDeclined(category)


def _usage_tokens(usage: Any) -> dict[str, int]:
    return {
        "input_tokens": getattr(usage, "input_tokens", None) or 0,
        "output_tokens": getattr(usage, "output_tokens", None) or 0,
        "cache_read_tokens": getattr(usage, "cache_read_input_tokens", None) or 0,
        "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", None) or 0,
    }


async def _settle_from_usage(line: MeteredLine, message: Any) -> None:
    """Settle at the response's real cost. When the response lists iterations (a fallback
    ran despite the setting), each is priced by its own model and the costs summed."""
    usage = message.usage
    iterations = getattr(usage, "iterations", None)
    if iterations:
        total = sum(
            claude_cost_micros(getattr(it, "model", None) or message.model, **_usage_tokens(it))
            for it in iterations
        )
        await line.settle_cost(total)
    else:
        await line.settle_usage(model=message.model, **_usage_tokens(usage))


async def _failure(exc: BaseException, line: MeteredLine, *, output_started: bool) -> BaseException:
    """Settle a failed call by the billing rule; return the exception to raise."""
    if classify_anthropic_error(exc, output_started=output_started) is Billing.UNBILLED:
        await line.settle_unbilled(type(exc).__name__)
    if is_provider_outage(exc):
        status = getattr(exc, "status_code", None)
        logger.warning("Claude call failed: %s (status %s)", type(exc).__name__, status)
        return LiveAIUnavailable(log_detail=f"Claude call failed: {type(exc).__name__}")
    return exc


async def _keep_reservation_if_unsettled(line: MeteredLine) -> None:
    if not line.settled:  # canceled, timed out, or unknown: keep the whole reservation
        with anyio.CancelScope(shield=True):
            await line.settle_reserved(_UNSETTLED)


async def stream_text(
    client: AsyncAnthropic, *, system: str, user: str, max_tokens: int, line: MeteredLine
) -> AsyncGenerator[str, None]:
    """Stream prose, yielding text deltas only. The raw events are read (not the SDK's
    `text_stream`) so a thinking block counts as output started and the deadline applies
    while the model thinks. A decline or a hit token cap is checked once the stream ends
    (after its usage is settled): text already sent stays on screen and the route's error
    frame follows it, so nothing is persisted."""
    line.mark_started()
    output_started = False
    deadline = time.monotonic() + settings.ai_stream_deadline_s
    manager = client.beta.messages.stream(  # type: ignore[call-overload]
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        timeout=stream_timeout(),
        **request_options(),
    )
    try:
        stream = await manager.__aenter__()
        try:
            async for event in stream:
                if event.type in _CONTENT_EVENTS:
                    # Any content, thinking included, is billed output: from here an
                    # overloaded error no longer settles to $0.
                    output_started = True
                    if event.type == "content_block_delta" and event.delta.type == "text_delta":
                        yield event.delta.text
                # Checked on every event, so a long thinking stretch is bounded too.
                if time.monotonic() > deadline:
                    raise StreamDeadlineExceeded
            final = await stream.get_final_message()
        finally:
            # Shielded and bounded, so a cancel can't leave the upstream call generating.
            with anyio.move_on_after(_CLOSE_TIMEOUT_S, shield=True):
                await manager.__aexit__(None, None, None)
        await _settle_from_usage(line, final)  # billed: settle first
        _raise_if_declined(final)
        if final.stop_reason == "max_tokens":
            # Thinking counts toward the cap; cut-off prose must not be saved as done.
            raise RuntimeError(f"Streamed output hit the {max_tokens}-token cap.")
    except _CALL_ERRORS as exc:
        err = await _failure(exc, line, output_started=output_started)
        if err is exc:
            raise
        raise err from exc
    except StreamDeadlineExceeded as exc:
        logger.warning("Claude stream passed its %s s deadline", settings.ai_stream_deadline_s)
        raise LiveAIUnavailable(log_detail="Claude stream passed its deadline") from exc
    finally:
        await _keep_reservation_if_unsettled(line)


async def structured_call(
    client: AsyncAnthropic,
    *,
    system: str,
    content: str | list[dict[str, Any]],
    tool: dict[str, Any],
    max_tokens: int,
    line: MeteredLine,
) -> dict[str, Any]:
    """One request whose reply is JSON matching `tool["input_schema"]`. The usage is
    settled as soon as the response arrives, before the decline, cap, and JSON checks."""
    options = request_options()
    options["output_config"]["format"] = {"type": "json_schema", "schema": tool["input_schema"]}
    line.mark_started()
    try:
        try:
            message = await client.beta.messages.create(  # type: ignore[call-overload]
                max_tokens=max_tokens,
                system=structured_system(system, tool),
                messages=cast("list[BetaMessageParam]", [{"role": "user", "content": content}]),
                **options,
            )
        except _CALL_ERRORS as exc:
            err = await _failure(exc, line, output_started=False)
            if err is exc:
                raise
            raise err from exc
        await _settle_from_usage(line, message)  # billed: settle first
    finally:
        await _keep_reservation_if_unsettled(line)
    _raise_if_declined(message)
    if message.stop_reason == "max_tokens":
        raise RuntimeError(f"{tool['name']} output hit the {max_tokens}-token cap.")
    # Read by type: with adaptive thinking a response can open with a thinking block.
    for block in message.content:
        if block.type == "text":
            return dict(json.loads(block.text))
    raise RuntimeError(f"Model returned no JSON for {tool['name']}.")
