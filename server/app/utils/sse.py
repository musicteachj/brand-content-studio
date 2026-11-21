"""Shared SSE plumbing (ARCH-02).

All four streamed-generation routes (text/card/post/document) frame their events
the same way and MUST end every response with a terminal `[DONE]` frame so the
client unsticks even on error (ARCHITECTURE gotcha #3). Owning that invariant here,
together with the SEC-07-redacted error frame, means a new generate route can't
drift or forget it. Each route provides only a domain *event generator* that yields
`{"text": ...}` per token, `{"error": ...}` for a handled stop, and `{"meta": ...}`
at the end; `sse_response` does the rest.

Two more duties live here:

- Heartbeats. While the model is silent (thinking, or a slow structured call), an SSE
  comment goes out every `HEARTBEAT_INTERVAL_S`, so proxies and the load balancer keep
  the connection open and a visitor who left is noticed on the next send. The client
  parser drops comment frames.
- Prompt settling on disconnect. Every route settles its ledger lines in its event
  generator's `finally`. Starlette cancels the body on disconnect only for ASGI spec
  versions below 2.4; from 2.4 on, `send` raises `OSError` and the generator would wait
  for garbage collection. `_ClosingStreamingResponse` closes it at once in both cases,
  and the framing generator closes the route's generator in its own `finally`, so the
  close reaches it wherever the stream stopped. A visitor can also leave before the body
  is first read, when the route's generator has not started and its `finally` cannot
  run; the route passes `on_close` (its ledger `finalize`) for that, and the response
  runs it once on every exit path.
"""
import asyncio
import json
import logging
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from typing import Any

import anyio
from fastapi.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from app.utils.errors import UserFacingError, client_error

logger = logging.getLogger(__name__)

# no-cache/keep-alive + disable proxy buffering so tokens flush live.
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
# The bare terminal sentinel the client reader matches to close the stream. Not
# JSON, so it is emitted as a literal (never routed through `frame`).
DONE = "data: [DONE]\n\n"
# An SSE comment: keeps the connection alive and carries no event.
HEARTBEAT = ": keep-alive\n\n"
HEARTBEAT_INTERVAL_S = 10.0


def frame(payload: dict) -> str:
    """Serialize one SSE `data:` line. Bare `json.dumps` (no kwargs) to match the
    exact wire bytes the client decodes; each frame carries one of text/meta/error."""
    return f"data: {json.dumps(payload)}\n\n"


class _ClosingStreamingResponse(StreamingResponse):
    def __init__(
        self, content: Any, *, on_close: Callable[[], Awaitable[None]] | None = None, **kwargs: Any
    ) -> None:
        super().__init__(content, **kwargs)
        self._on_close = on_close

    async def stream_response(self, send: Send) -> None:
        try:
            await super().stream_response(send)
        finally:  # run the generators' finally blocks (settles) now, whatever ended the stream
            with anyio.CancelScope(shield=True):
                await self.body_iterator.aclose()  # type: ignore[attr-defined]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Awaited by the app itself (not in a task Starlette may cancel before it starts),
        # so this `finally` runs on every exit path, a body that never started included.
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await self.body_iterator.aclose()  # type: ignore[attr-defined]
                on_close, self._on_close = self._on_close, None
                if on_close is not None:
                    await on_close()


async def _with_heartbeats(frames: AsyncIterator[str], interval_s: float) -> AsyncIterator[str]:
    """Pass `frames` through, adding a `HEARTBEAT` after each `interval_s` without one.
    The pending frame is awaited in its own task so a heartbeat never cancels the model
    call; on close, that task is canceled once and awaited, so the routes' settles run."""
    it = frames.__aiter__()
    pending: asyncio.Task[str] | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(it.__anext__())
            done, _ = await asyncio.wait({pending}, timeout=interval_s)  # never cancels pending
            if not done:
                yield HEARTBEAT
                continue
            task, pending = pending, None
            try:
                chunk = task.result()
            except StopAsyncIteration:
                return
            yield chunk
    finally:
        with anyio.CancelScope(shield=True):
            if pending is not None and not pending.done():
                pending.cancel()  # one native cancel; the inner finally settles (shielded)
                await asyncio.wait({pending})
            try:
                await it.aclose()  # type: ignore[attr-defined]
            except Exception:
                logger.exception("closing an SSE event stream failed")


def _error_frame(exc: UserFacingError) -> str:
    payload: dict = {"error": exc.message}
    if exc.code is not None:
        payload["code"] = exc.code
    return frame(payload)


def sse_response(
    events: AsyncGenerator[dict, None],
    *,
    context: str,
    heartbeat_s: float = HEARTBEAT_INTERVAL_S,
    on_close: Callable[[], Awaitable[None]] | None = None,
) -> StreamingResponse:
    """Wrap a domain event generator as an SSE `StreamingResponse`. Frames each
    event; converts any unhandled exception into a single redacted error frame
    (SEC-07, `context` labels the log entry); always emits the terminal `[DONE]`
    so the client unsticks on success and failure alike; sends a heartbeat comment
    after each `heartbeat_s` of silence; closes the event generator as soon as the
    stream ends, a disconnect included; and awaits `on_close` once at the very end,
    even when the event generator never started."""

    async def run() -> AsyncGenerator[str, None]:
        try:
            async for event in events:
                yield frame(event)
        except UserFacingError as exc:
            # An expected failure (a model decline, DECISIONS #40, or a budget refusal)
            # is said plainly instead of the redacted "Something went wrong", with its
            # code when it has one.
            yield _error_frame(exc)
        except Exception as exc:
            yield frame({"error": client_error(exc, context=context)})
        finally:
            # However this generator ends (a consumer that stops right after a frame
            # included), close the route's generator now so its `finally` settles at once.
            # No yield in here: a yield would ignore that close.
            with anyio.CancelScope(shield=True):
                await events.aclose()
        yield DONE

    return _ClosingStreamingResponse(
        _with_heartbeats(run(), heartbeat_s),
        on_close=on_close,
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
