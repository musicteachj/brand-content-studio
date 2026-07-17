"""Shared SSE plumbing (ARCH-02).

All four streamed-generation routes (text/card/post/document) frame their events
the same way and MUST end every response with a terminal `[DONE]` frame so the
client unsticks even on error (ARCHITECTURE gotcha #3). Owning that invariant here
— together with the SEC-07-redacted error frame — means a new generate route can't
drift or forget it. Each route provides only a domain *event generator* that yields
`{"text": ...}` per token, `{"error": ...}` for a handled stop, and `{"meta": ...}`
at the end; `sse_response` does the rest.
"""
import json
from collections.abc import AsyncGenerator

from fastapi.responses import StreamingResponse

from app.utils.errors import client_error

# no-cache/keep-alive + disable proxy buffering so tokens flush live.
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
# The bare terminal sentinel the client reader matches to close the stream. Not
# JSON, so it is emitted as a literal (never routed through `frame`).
DONE = "data: [DONE]\n\n"


def frame(payload: dict) -> str:
    """Serialize one SSE `data:` line. Bare `json.dumps` (no kwargs) to match the
    exact wire bytes the client decodes; each frame carries one of text/meta/error."""
    return f"data: {json.dumps(payload)}\n\n"


def sse_response(events: AsyncGenerator[dict, None], *, context: str) -> StreamingResponse:
    """Wrap a domain event generator as an SSE `StreamingResponse`. Frames each
    event; converts any unhandled exception into a single redacted error frame
    (SEC-07, `context` labels the log entry); and always emits the terminal `[DONE]`
    so the client unsticks on success and failure alike."""

    async def run() -> AsyncGenerator[str, None]:
        try:
            async for event in events:
                yield frame(event)
        except Exception as exc:
            yield frame({"error": client_error(exc, context=context)})
        finally:
            yield DONE

    return StreamingResponse(run(), media_type="text/event-stream", headers=SSE_HEADERS)
