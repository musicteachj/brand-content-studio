"""The shared SSE wrapper (ARCH-02). `sse_response` owns the framing, the
SEC-07-redacted error frame, and the terminal `[DONE]` invariant so no generate
route can drift or forget them — the paths the route tests don't cover."""
import pytest
from starlette.responses import StreamingResponse

from app.utils.sse import DONE, frame, sse_response


async def _collect(response: StreamingResponse) -> str:
    parts: list[str] = []
    async for chunk in response.body_iterator:
        parts.append(chunk if isinstance(chunk, str) else chunk.decode())
    return "".join(parts)


def test_frame_serializes_a_data_line_with_bare_json():
    assert frame({"text": "hi"}) == 'data: {"text": "hi"}\n\n'
    assert frame({"meta": {"k": 1}}) == 'data: {"meta": {"k": 1}}\n\n'


def test_sse_response_sets_stream_headers_and_media_type():
    async def produce():
        yield {"text": "x"}

    resp = sse_response(produce(), context="ctx")
    assert resp.media_type == "text/event-stream"
    assert resp.headers["cache-control"] == "no-cache"
    assert resp.headers["connection"] == "keep-alive"
    assert resp.headers["x-accel-buffering"] == "no"


@pytest.mark.asyncio
async def test_sse_response_frames_events_then_terminates_with_done():
    async def produce():
        yield {"text": "Hello "}
        yield {"text": "world"}
        yield {"meta": {"generation_id": "g1"}}

    body = await _collect(sse_response(produce(), context="ctx"))
    assert body == (
        'data: {"text": "Hello "}\n\n'
        'data: {"text": "world"}\n\n'
        'data: {"meta": {"generation_id": "g1"}}\n\n'
        "data: [DONE]\n\n"
    )
    assert body.endswith(DONE)


@pytest.mark.asyncio
async def test_sse_response_redacts_an_exception_and_still_emits_done():
    async def produce():
        yield {"text": "partial"}
        raise RuntimeError("secret internal detail: db=postgres://user:pw@host")

    body = await _collect(sse_response(produce(), context="unit test"))
    frames = [line for line in body.split("\n\n") if line]
    assert frames[0] == 'data: {"text": "partial"}'
    # SEC-07: the raw exception is never sent; a generic message + correlation id is.
    assert "secret internal detail" not in body
    assert "postgres://" not in body
    assert '"error"' in frames[1]
    assert "ref:" in frames[1]
    assert frames[-1] == "data: [DONE]"


@pytest.mark.asyncio
async def test_sse_response_passes_through_a_domain_error_event_then_done():
    async def produce():
        yield {"error": "No brand context could be retrieved for this brief."}

    body = await _collect(sse_response(produce(), context="ctx"))
    assert 'data: {"error": "No brand context could be retrieved for this brief."}\n\n' in body
    assert body.endswith(DONE)
