"""The shared Claude request shape (DECISIONS #40). Route tests replace the
services with fakes, so this is where the real request is checked: the model,
effort, no server-side fallback, structured output instead of a forced tool, reading
blocks by type, and turning a decline into `ModelDeclined`. No network: a fake
stands in for `client.beta.messages`."""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import anyio
import httpx
import pytest

from app.config import Settings, settings
from app.main import _user_facing_error_handler, app
from app.services import claude_calls
from app.services.claude_calls import DECLINED_MESSAGE, ModelDeclined
from app.utils.errors import LiveAIUnavailable, UserFacingError
from tests.test_ai_failures import (
    auth_401,
    bad_request_400,
    connection_error,
    overloaded_529,
    overloaded_mid_stream,
    permission_403,
    rate_limit_429,
    status_402,
    timeout_error,
)

TOOL: dict[str, Any] = {
    "name": "card_fields",
    "description": "Record the structured copy for a card.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"headline": {"type": "string"}},
        "required": ["headline"],
    },
}


USAGE = SimpleNamespace(
    input_tokens=1_000, output_tokens=200, cache_read_input_tokens=None, cache_creation_input_tokens=None
)


def _message(*blocks: Any, stop_reason: str = "end_turn", category: str | None = None) -> Any:
    details = SimpleNamespace(category=category) if stop_reason == "refusal" else None
    return SimpleNamespace(
        content=list(blocks),
        stop_reason=stop_reason,
        stop_details=details,
        model="claude-sonnet-5-5",
        usage=USAGE,
    )


def _text(text: str) -> Any:
    return SimpleNamespace(type="text", text=text)


THINKING = SimpleNamespace(type="thinking", thinking="")


class RecordingLine:
    """Stands in for `MeteredLine`: records how (and whether) the call was settled. Like the
    real line, only the first settle counts."""

    def __init__(self) -> None:
        self.started = False
        self.settled = False
        self.how: str | None = None
        self.args: dict[str, Any] = {}

    def mark_started(self) -> None:
        self.started = True

    def _record(self, how: str, **args: Any) -> None:
        if self.settled:
            return
        self.settled = True
        self.how = how
        self.args = args

    async def settle_usage(self, **kwargs: Any) -> None:
        self._record("usage", **kwargs)

    async def settle_cost(self, actual_micros: int) -> None:
        self._record("cost", actual_micros=actual_micros)

    async def settle_unbilled(self, outcome: str) -> None:
        self._record("unbilled", outcome=outcome)

    async def settle_reserved(self, outcome: str) -> None:
        self._record("reserved", outcome=outcome)


MESSAGE_START = SimpleNamespace(type="message_start")


def _thinking(text: str = "...") -> Any:
    return SimpleNamespace(
        type="content_block_delta", index=0, delta=SimpleNamespace(type="thinking_delta", thinking=text)
    )


def _events(items: list[Any]) -> list[Any]:
    """Shape a fake stream the way the SDK's message stream iterates: a `message_start`,
    then for each string a raw `text_delta` followed by the SDK's own `text` event (which
    must not be yielded twice); other items (thinking deltas) pass through as they are."""
    out: list[Any] = [MESSAGE_START]
    for item in items:
        if isinstance(item, str):
            out.append(
                SimpleNamespace(
                    type="content_block_delta", index=1, delta=SimpleNamespace(type="text_delta", text=item)
                )
            )
            out.append(SimpleNamespace(type="text", text=item, snapshot=item))
        else:
            out.append(item)
    return out


class _FakeStream:
    """Stands in for the SDK's message stream: async-iterable over events, plus
    `get_final_message()`."""

    def __init__(self, events: Any, final: Any) -> None:
        self._events = events
        self._final = final

    def __aiter__(self) -> Any:
        return self._events

    async def get_final_message(self) -> Any:
        return self._final


class _StreamCtx:
    """Stands in for the SDK's stream manager: `async with` yields a `_FakeStream`.
    `items` are text deltas (strings) or other events (`_thinking()`). `enter_error`
    fails the request itself; `stream_error` fails after the items; `hold` makes the
    stream wait on an event after its items (to cancel it there)."""

    def __init__(
        self,
        items: list[Any],
        final: Any,
        *,
        enter_error: BaseException | None = None,
        stream_error: BaseException | None = None,
        hold: anyio.Event | None = None,
        waiting: anyio.Event | None = None,
    ) -> None:
        self.enter_error = enter_error
        self.exited = False

        async def events():  # type: ignore[no-untyped-def]
            for event in _events(items):
                yield event
            if hold is not None:
                if waiting is not None:
                    waiting.set()
                await hold.wait()
            if stream_error is not None:
                raise stream_error

        self._stream = _FakeStream(events(), final)

    async def __aenter__(self) -> Any:
        if self.enter_error is not None:
            raise self.enter_error
        return self._stream

    async def __aexit__(self, *exc: object) -> None:
        self.exited = True


class _FakeMessages:
    def __init__(
        self,
        *,
        reply: Any = None,
        deltas: list[Any] | None = None,
        error: BaseException | None = None,
        stream_error: BaseException | None = None,
        hold: anyio.Event | None = None,
    ) -> None:
        self.reply = reply
        self.deltas = deltas or []
        self.error = error
        self.stream_error = stream_error
        self.hold = hold
        self.waiting = anyio.Event()
        self.calls: list[dict[str, Any]] = []
        self.manager: _StreamCtx | None = None

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.reply

    def stream(self, **kwargs: Any) -> _StreamCtx:
        self.calls.append(kwargs)
        self.manager = _StreamCtx(
            self.deltas,
            self.reply,
            enter_error=self.error,
            stream_error=self.stream_error,
            hold=self.hold,
            waiting=self.waiting,
        )
        return self.manager


def _client(messages: _FakeMessages) -> Any:
    return SimpleNamespace(beta=SimpleNamespace(messages=messages))


def test_defaults_are_sonnet_5_5_at_low_effort():
    defaults = Settings(_env_file=None)  # type: ignore[call-arg]
    assert defaults.ai_model == "claude-sonnet-5-5"
    assert defaults.ai_effort == "low"


@pytest.mark.asyncio
async def test_structured_call_request_shape():
    msgs = _FakeMessages(reply=_message(_text('{"headline": "Hi"}')))
    await claude_calls.structured_call(
        _client(msgs), system="SYS", content="brief", tool=TOOL, max_tokens=4000, line=RecordingLine()
    )
    call = msgs.calls[0]
    assert call["model"] == settings.ai_model
    assert call["max_tokens"] == 4000
    assert call["output_config"] == {
        "effort": settings.ai_effort,
        "format": {"type": "json_schema", "schema": TOOL["input_schema"]},
    }
    assert "betas" not in call and "fallbacks" not in call
    # Sonnet 5.5 rejects a forced tool_choice; nothing tool-shaped is sent.
    for key in ("tool_choice", "tools", "thinking", "temperature"):
        assert key not in call
    # The tool's description survives as an instruction.
    assert call["system"].startswith("SYS")
    assert TOOL["description"] in call["system"]
    assert call["messages"] == [{"role": "user", "content": "brief"}]


@pytest.mark.asyncio
async def test_structured_call_reads_json_after_a_thinking_block():
    msgs = _FakeMessages(reply=_message(THINKING, _text(json.dumps({"headline": "Cork"}))))
    out = await claude_calls.structured_call(
        _client(msgs), system="s", content="b", tool=TOOL, max_tokens=10, line=RecordingLine()
    )
    assert out == {"headline": "Cork"}


@pytest.mark.asyncio
async def test_structured_call_does_not_share_output_config_between_calls():
    msgs = _FakeMessages(reply=_message(_text("{}")))
    await claude_calls.structured_call(_client(msgs), system="s", content="b", tool=TOOL, max_tokens=10, line=RecordingLine())
    assert claude_calls.request_options()["output_config"] == {"effort": settings.ai_effort}


@pytest.mark.asyncio
async def test_structured_call_refusal_raises_model_declined():
    msgs = _FakeMessages(reply=_message(stop_reason="refusal", category="cyber"))
    with pytest.raises(ModelDeclined) as info:
        await claude_calls.structured_call(
            _client(msgs), system="s", content="b", tool=TOOL, max_tokens=10, line=RecordingLine()
        )
    assert info.value.category == "cyber"
    assert info.value.message == DECLINED_MESSAGE


@pytest.mark.asyncio
async def test_structured_call_refusal_with_null_details_still_raises():
    reply = SimpleNamespace(
        content=[], stop_reason="refusal", stop_details=None, model="claude-sonnet-5-5", usage=USAGE
    )
    with pytest.raises(ModelDeclined):
        await claude_calls.structured_call(
            _client(_FakeMessages(reply=reply)), system="s", content="b", tool=TOOL, max_tokens=10, line=RecordingLine()
        )


@pytest.mark.asyncio
async def test_structured_call_hitting_the_cap_raises():
    msgs = _FakeMessages(reply=_message(_text('{"head'), stop_reason="max_tokens"))
    with pytest.raises(RuntimeError, match="4000-token cap"):
        await claude_calls.structured_call(
            _client(msgs), system="s", content="b", tool=TOOL, max_tokens=4000, line=RecordingLine()
        )


@pytest.mark.asyncio
async def test_structured_call_with_no_text_block_raises():
    msgs = _FakeMessages(reply=_message(THINKING))
    with pytest.raises(RuntimeError, match="no JSON"):
        await claude_calls.structured_call(
            _client(msgs), system="s", content="b", tool=TOOL, max_tokens=10, line=RecordingLine()
        )


@pytest.mark.asyncio
async def test_stream_text_yields_deltas_with_the_shared_options():
    msgs = _FakeMessages(reply=_message(_text("Hello world")), deltas=["Hello ", "world"])
    out = [
        t async for t in claude_calls.stream_text(
            _client(msgs), system="SYS", user="brief", max_tokens=2000, line=RecordingLine()
        )
    ]
    assert out == ["Hello ", "world"]
    call = msgs.calls[0]
    assert call["model"] == settings.ai_model
    assert call["output_config"] == {"effort": settings.ai_effort}
    assert "betas" not in call and "fallbacks" not in call
    assert call["system"] == "SYS"
    assert call["max_tokens"] == 2000


@pytest.mark.asyncio
async def test_stream_sets_a_per_request_read_timeout():
    msgs = _FakeMessages(reply=_message(_text("Hi")), deltas=["Hi"])
    _ = [
        t async for t in claude_calls.stream_text(
            _client(msgs), system="s", user="b", max_tokens=10, line=RecordingLine()
        )
    ]
    assert msgs.calls[0]["timeout"].read == settings.ai_stream_read_timeout_s


@pytest.mark.asyncio
async def test_stream_text_hitting_the_cap_raises_after_the_text():
    msgs = _FakeMessages(reply=_message(_text("cut"), stop_reason="max_tokens"), deltas=["cut"])
    seen: list[str] = []
    with pytest.raises(RuntimeError, match="2000-token cap"):
        async for t in claude_calls.stream_text(
            _client(msgs), system="s", user="b", max_tokens=2000, line=RecordingLine()
        ):
            seen.append(t)
    assert seen == ["cut"]


@pytest.mark.asyncio
async def test_stream_text_refusal_raises_after_the_partial_text():
    msgs = _FakeMessages(reply=_message(stop_reason="refusal"), deltas=["partial"])
    seen: list[str] = []
    with pytest.raises(ModelDeclined):
        async for t in claude_calls.stream_text(
            _client(msgs), system="s", user="b", max_tokens=10, line=RecordingLine()
        ):
            seen.append(t)
    assert seen == ["partial"]


@pytest.mark.asyncio
async def test_model_declined_is_a_readable_422_on_non_streaming_routes():
    assert isinstance(ModelDeclined(), UserFacingError)
    assert app.exception_handlers[UserFacingError] is _user_facing_error_handler
    resp = await _user_facing_error_handler(None, ModelDeclined("general_harms"))  # type: ignore[arg-type]
    assert resp.status_code == 422
    assert json.loads(bytes(resp.body)) == {"detail": DECLINED_MESSAGE}
    # The category goes to the log, never to the client.
    assert "general_harms" not in bytes(resp.body).decode()
    assert "general_harms" in str(ModelDeclined("general_harms"))


# --- metering: every call settles exactly once ---------------------------------
USAGE_ARGS = {"input_tokens": 1_000, "output_tokens": 200, "cache_read_tokens": 0, "cache_write_tokens": 0}


async def _drain(gen: Any) -> list[str]:
    return [t async for t in gen]


def _stream(msgs: _FakeMessages, line: RecordingLine) -> Any:
    return claude_calls.stream_text(_client(msgs), system="s", user="b", max_tokens=10, line=line)


def _structured(msgs: _FakeMessages, line: RecordingLine) -> Any:
    return claude_calls.structured_call(
        _client(msgs), system="s", content="b", tool=TOOL, max_tokens=10, line=line
    )


async def test_a_finished_stream_settles_from_usage():
    line = RecordingLine()
    msgs = _FakeMessages(reply=_message(_text("Hi")), deltas=["Hi"])
    assert await _drain(_stream(msgs, line)) == ["Hi"]
    assert line.started
    assert (line.how, line.args) == ("usage", {"model": "claude-sonnet-5-5", **USAGE_ARGS})


async def test_stream_settles_usage_before_a_decline_is_raised():
    line = RecordingLine()
    msgs = _FakeMessages(reply=_message(stop_reason="refusal"), deltas=["partial"])
    with pytest.raises(ModelDeclined):
        await _drain(_stream(msgs, line))
    assert (line.how, line.args) == ("usage", {"model": "claude-sonnet-5-5", **USAGE_ARGS})


async def test_stream_settles_usage_before_a_token_cap_error():
    line = RecordingLine()
    msgs = _FakeMessages(reply=_message(_text("cut"), stop_reason="max_tokens"), deltas=["cut"])
    with pytest.raises(RuntimeError, match="token cap"):
        await _drain(_stream(msgs, line))
    assert line.how == "usage"


async def test_usage_with_iterations_prices_each_iteration_by_its_own_model():
    iterations = [
        SimpleNamespace(model="claude-sonnet-5-5", input_tokens=1_000, output_tokens=0,
                        cache_read_input_tokens=0, cache_creation_input_tokens=0),
        SimpleNamespace(model="claude-opus-5-5", input_tokens=1_000, output_tokens=100,
                        cache_read_input_tokens=0, cache_creation_input_tokens=0),
    ]
    reply = _message(_text("{}"))
    reply.usage = SimpleNamespace(**vars(USAGE), iterations=iterations)
    line = RecordingLine()
    await _structured(_FakeMessages(reply=reply), line)
    # Sonnet 1,000 x 2 + Opus (1,000 x 4 + 100 x 20).
    assert (line.how, line.args) == ("cost", {"actual_micros": 2_000 + 4_000 + 2_000})


@pytest.mark.parametrize(
    "reply, error",
    [
        (_message(stop_reason="refusal"), ModelDeclined),
        (_message(_text('{"head'), stop_reason="max_tokens"), RuntimeError),
        (_message(_text("not json")), json.JSONDecodeError),
    ],
)
async def test_structured_call_settles_before_decline_cap_or_bad_json(reply, error):
    line = RecordingLine()
    with pytest.raises(error):
        await _structured(_FakeMessages(reply=reply), line)
    assert line.started
    assert (line.how, line.args) == ("usage", {"model": "claude-sonnet-5-5", **USAGE_ARGS})


UNBILLED_ERRORS = [
    auth_401(),
    permission_403(),
    status_402(),
    bad_request_400("You have reached your specified workspace API usage limits."),
    bad_request_400("Your credit balance is too low to access the Anthropic API."),
    rate_limit_429(body={}),
    overloaded_529(),
]


@pytest.mark.parametrize("exc", UNBILLED_ERRORS)
@pytest.mark.parametrize("kind", ["stream", "structured"])
async def test_unbilled_errors_settle_to_zero_and_raise_live_ai_unavailable(kind, exc):
    line = RecordingLine()
    msgs = _FakeMessages(reply=_message(_text("{}")), error=exc)
    with pytest.raises(LiveAIUnavailable) as info:
        if kind == "stream":
            await _drain(_stream(msgs, line))
        else:
            await _structured(msgs, line)
    assert (line.how, line.args) == ("unbilled", {"outcome": type(exc).__name__})
    assert info.value.__cause__ is exc


@pytest.mark.parametrize("exc", [timeout_error(), connection_error(), httpx.ReadTimeout("x")])
@pytest.mark.parametrize("kind", ["stream", "structured", "mid_stream"])
async def test_timeouts_and_connection_errors_keep_the_reservation(kind, exc):
    line = RecordingLine()
    if kind == "mid_stream":
        msgs = _FakeMessages(reply=_message(_text("Hi")), deltas=["Hi"], stream_error=exc)
    else:
        msgs = _FakeMessages(reply=_message(_text("{}")), error=exc)
    with pytest.raises(LiveAIUnavailable):
        if kind == "structured":
            await _structured(msgs, line)
        else:
            await _drain(_stream(msgs, line))
    assert (line.how, line.args) == ("reserved", {"outcome": "canceled_or_unknown"})


async def test_overloaded_after_output_keeps_the_reservation():
    line = RecordingLine()
    msgs = _FakeMessages(reply=_message(_text("Hi")), deltas=["Hi"], stream_error=overloaded_529())
    with pytest.raises(LiveAIUnavailable):
        await _drain(_stream(msgs, line))
    assert line.how == "reserved"


@pytest.mark.parametrize("kind", ["stream", "structured"])
async def test_other_bad_requests_keep_the_reservation_and_reraise_the_original(kind):
    exc = bad_request_400("invalid model: claude-x")
    line = RecordingLine()
    msgs = _FakeMessages(reply=_message(_text("{}")), error=exc)
    with pytest.raises(type(exc)) as info:
        if kind == "stream":
            await _drain(_stream(msgs, line))
        else:
            await _structured(msgs, line)
    assert info.value is exc
    assert (line.how, line.args) == ("reserved", {"outcome": "canceled_or_unknown"})


async def test_a_canceled_stream_settles_at_the_reserved_amount_and_closes_the_sdk_stream():
    line = RecordingLine()
    msgs = _FakeMessages(reply=_message(_text("Hi")), deltas=["Hi"], hold=anyio.Event())
    seen: list[str] = []

    async def consume() -> None:
        async for t in _stream(msgs, line):
            seen.append(t)

    async with anyio.create_task_group() as tg:
        tg.start_soon(consume)
        with anyio.fail_after(5):
            await msgs.waiting.wait()
        tg.cancel_scope.cancel()

    assert seen == ["Hi"]
    assert msgs.manager is not None and msgs.manager.exited
    assert (line.how, line.args) == ("reserved", {"outcome": "canceled_or_unknown"})


async def test_the_stream_deadline_keeps_the_reservation(monkeypatch):
    monkeypatch.setattr(settings, "ai_stream_deadline_s", 0)
    line = RecordingLine()
    msgs = _FakeMessages(reply=_message(_text("a b c")), deltas=["a ", "b ", "c"])
    seen: list[str] = []
    with pytest.raises(LiveAIUnavailable):
        async for t in _stream(msgs, line):
            seen.append(t)
    # Checked on every event, so the opening message_start already trips a 0 s deadline.
    assert seen == []
    assert msgs.manager is not None and msgs.manager.exited
    assert (line.how, line.args) == ("reserved", {"outcome": "canceled_or_unknown"})


# --- thinking counts as output (fix round 1) -------------------------------------
async def test_thinking_is_never_yielded_and_text_is_yielded_once():
    msgs = _FakeMessages(reply=_message(_text("Hi there")), deltas=[_thinking(), "Hi ", "there"])
    assert await _drain(_stream(msgs, RecordingLine())) == ["Hi ", "there"]


async def test_overloaded_before_any_content_settles_to_zero():
    # Only the message_start bookkeeping event arrived: nothing was generated.
    line = RecordingLine()
    msgs = _FakeMessages(reply=_message(_text("x")), deltas=[], stream_error=overloaded_mid_stream())
    with pytest.raises(LiveAIUnavailable):
        await _drain(_stream(msgs, line))
    assert (line.how, line.args) == ("unbilled", {"outcome": "APIStatusError"})


async def test_overloaded_after_thinking_only_keeps_the_reservation():
    # Thinking tokens are billed output, even with no text yet.
    line = RecordingLine()
    msgs = _FakeMessages(
        reply=_message(_text("x")), deltas=[_thinking(), _thinking()], stream_error=overloaded_mid_stream()
    )
    seen: list[str] = []
    with pytest.raises(LiveAIUnavailable):
        async for t in _stream(msgs, line):
            seen.append(t)
    assert seen == []
    assert (line.how, line.args) == ("reserved", {"outcome": "canceled_or_unknown"})


async def test_the_deadline_fires_during_a_thinking_only_stretch(monkeypatch):
    monkeypatch.setattr(settings, "ai_stream_deadline_s", 0)
    line = RecordingLine()
    msgs = _FakeMessages(reply=_message(_text("x")), deltas=[_thinking(), _thinking(), "late"])
    seen: list[str] = []
    with pytest.raises(LiveAIUnavailable):
        async for t in _stream(msgs, line):
            seen.append(t)
    assert seen == []
    assert msgs.manager is not None and msgs.manager.exited
    assert (line.how, line.args) == ("reserved", {"outcome": "canceled_or_unknown"})
