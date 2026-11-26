"""The shared SSE wrapper (ARCH-02). `sse_response` owns the framing, the
SEC-07-redacted error frame, and the terminal `[DONE]` invariant so no generate
route can drift or forget them: the paths the route tests don't cover."""
import asyncio

import pytest
from starlette.requests import ClientDisconnect
from starlette.responses import StreamingResponse

from app.utils.errors import BudgetRefusal
from app.utils.sse import DONE, HEARTBEAT, HEARTBEAT_INTERVAL_S, frame, sse_response


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


@pytest.mark.asyncio
async def test_sse_response_reports_a_model_decline_readably_then_done():
    """A decline isn't a server fault (DECISIONS #40): the user gets the plain
    message, not the redacted "Something went wrong" with a ref."""
    from app.services.claude_calls import DECLINED_MESSAGE, ModelDeclined

    async def produce():
        yield {"text": "partial"}
        raise ModelDeclined("general_harms")

    body = await _collect(sse_response(produce(), context="ctx"))
    frames = [line for line in body.split("\n\n") if line]
    assert frames[0] == 'data: {"text": "partial"}'
    assert frames[1] == frame({"error": DECLINED_MESSAGE}).strip()
    assert "ref:" not in body
    assert frames[-1] == "data: [DONE]"


@pytest.mark.asyncio
async def test_a_coded_error_frame_carries_its_code():
    async def produce():
        yield {"text": "partial"}
        raise BudgetRefusal("visitor")

    body = await _collect(sse_response(produce(), context="ctx"))
    frames = [line for line in body.split("\n\n") if line]
    refusal = BudgetRefusal("visitor")
    assert frames[1] == frame({"error": refusal.message, "code": "visitor_allowance"}).strip()
    assert frames[-1] == "data: [DONE]"


def test_the_heartbeat_is_an_sse_comment_every_ten_seconds():
    assert HEARTBEAT == ": keep-alive\n\n"
    assert HEARTBEAT_INTERVAL_S == 10.0


@pytest.mark.asyncio
async def test_a_heartbeat_comment_is_sent_while_the_model_is_silent():
    async def slow():
        await asyncio.sleep(0.25)
        yield {"text": "hi"}

    body = await _collect(sse_response(slow(), context="t", heartbeat_s=0.05))
    assert body.count(": keep-alive\n\n") >= 3
    assert body.endswith('data: {"text": "hi"}\n\ndata: [DONE]\n\n')


@pytest.mark.asyncio
async def test_no_heartbeat_when_frames_keep_coming():
    async def steady():
        for i in range(5):
            await asyncio.sleep(0.01)
            yield {"text": str(i)}

    body = await _collect(sse_response(steady(), context="t", heartbeat_s=0.2))
    assert HEARTBEAT not in body
    assert body == "".join(frame({"text": str(i)}) for i in range(5)) + DONE


@pytest.mark.asyncio
async def test_closing_the_response_mid_wait_runs_the_event_generators_finally():
    """Whatever ends the stream, the domain generator's `finally` (where the routes
    settle their ledger lines) runs before `aclose` returns, not at garbage collection."""
    released = asyncio.Event()
    finished: list[str] = []

    async def stuck():
        try:
            yield {"text": "first"}
            await released.wait()
            yield {"text": "never"}
        finally:
            finished.append("finally")

    response = sse_response(stuck(), context="t", heartbeat_s=0.05)
    it = response.body_iterator
    assert await it.__anext__() == frame({"text": "first"})
    assert await it.__anext__() == HEARTBEAT
    await it.aclose()  # type: ignore[attr-defined]
    assert finished == ["finally"]


@pytest.mark.asyncio
async def test_stopping_right_after_a_data_frame_closes_the_event_generator_at_once():
    """The consumer stops just after a data frame (its send failed), so no frame is
    pending: closing must still reach the domain generator's `finally` at once."""
    finished: list[str] = []

    async def steady():
        try:
            while True:
                yield {"text": "x"}
        finally:
            finished.append("finally")

    it = sse_response(steady(), context="t").body_iterator
    assert await it.__anext__() == frame({"text": "x"})
    await it.aclose()  # type: ignore[attr-defined]
    assert finished == ["finally"]


async def _never() -> dict:
    await asyncio.Event().wait()
    raise AssertionError("unreachable")


_SCOPE_2_4 = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}}


@pytest.mark.asyncio
async def test_on_close_runs_once_when_the_stream_completes():
    closes: list[str] = []
    sent: list[dict] = []

    async def on_close() -> None:
        closes.append("closed")

    async def produce():
        yield {"text": "x"}

    async def send(message: dict) -> None:
        sent.append(message)

    await sse_response(produce(), context="t", on_close=on_close)(_SCOPE_2_4, _never, send)
    assert closes == ["closed"]
    assert sent[-1] == {"type": "http.response.body", "body": b"", "more_body": False}


@pytest.mark.asyncio
async def test_on_close_runs_when_the_body_never_starts():
    closes: list[str] = []
    started: list[str] = []

    async def on_close() -> None:
        closes.append("closed")

    async def produce():
        started.append("started")
        yield {"text": "x"}

    async def send(message: dict) -> None:
        raise OSError("client went away")

    with pytest.raises(ClientDisconnect):
        await sse_response(produce(), context="t", on_close=on_close)(_SCOPE_2_4, _never, send)
    assert started == []
    assert closes == ["closed"]
