"""The shared Claude request shape (DECISIONS #40). Route tests replace the
services with fakes, so this is where the real request is checked: the model,
effort, no server-side fallback, structured output instead of a forced tool, reading
blocks by type, and turning a decline into `ModelDeclined`. No network: a fake
stands in for `client.beta.messages`."""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from app.config import Settings, settings
from app.main import _user_facing_error_handler, app
from app.services import claude_calls
from app.services.claude_calls import DECLINED_MESSAGE, ModelDeclined
from app.utils.errors import UserFacingError

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


def _message(*blocks: Any, stop_reason: str = "end_turn", category: str | None = None) -> Any:
    details = SimpleNamespace(category=category) if stop_reason == "refusal" else None
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason, stop_details=details)


def _text(text: str) -> Any:
    return SimpleNamespace(type="text", text=text)


THINKING = SimpleNamespace(type="thinking", thinking="")


class _StreamCtx:
    """Stands in for the SDK's stream manager: `async with` yields an object with
    `text_stream` (async iterator of deltas) and `get_final_message()`."""

    def __init__(self, deltas: list[str], final: Any) -> None:
        async def text_stream():  # type: ignore[no-untyped-def]
            for d in deltas:
                yield d

        async def get_final_message() -> Any:
            return final

        self._stream = SimpleNamespace(
            text_stream=text_stream(), get_final_message=get_final_message
        )

    async def __aenter__(self) -> Any:
        return self._stream

    async def __aexit__(self, *exc: object) -> None:
        return None


class _FakeMessages:
    def __init__(self, *, reply: Any = None, deltas: list[str] | None = None) -> None:
        self.reply = reply
        self.deltas = deltas or []
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.reply

    def stream(self, **kwargs: Any) -> _StreamCtx:
        self.calls.append(kwargs)
        return _StreamCtx(self.deltas, self.reply)


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
        _client(msgs), system="SYS", content="brief", tool=TOOL, max_tokens=4000
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
        _client(msgs), system="s", content="b", tool=TOOL, max_tokens=10
    )
    assert out == {"headline": "Cork"}


@pytest.mark.asyncio
async def test_structured_call_does_not_share_output_config_between_calls():
    msgs = _FakeMessages(reply=_message(_text("{}")))
    await claude_calls.structured_call(_client(msgs), system="s", content="b", tool=TOOL, max_tokens=10)
    assert claude_calls.request_options()["output_config"] == {"effort": settings.ai_effort}


@pytest.mark.asyncio
async def test_structured_call_refusal_raises_model_declined():
    msgs = _FakeMessages(reply=_message(stop_reason="refusal", category="cyber"))
    with pytest.raises(ModelDeclined) as info:
        await claude_calls.structured_call(
            _client(msgs), system="s", content="b", tool=TOOL, max_tokens=10
        )
    assert info.value.category == "cyber"
    assert info.value.message == DECLINED_MESSAGE


@pytest.mark.asyncio
async def test_structured_call_refusal_with_null_details_still_raises():
    reply = SimpleNamespace(content=[], stop_reason="refusal", stop_details=None)
    with pytest.raises(ModelDeclined):
        await claude_calls.structured_call(
            _client(_FakeMessages(reply=reply)), system="s", content="b", tool=TOOL, max_tokens=10
        )


@pytest.mark.asyncio
async def test_structured_call_hitting_the_cap_raises():
    msgs = _FakeMessages(reply=_message(_text('{"head'), stop_reason="max_tokens"))
    with pytest.raises(RuntimeError, match="4000-token cap"):
        await claude_calls.structured_call(
            _client(msgs), system="s", content="b", tool=TOOL, max_tokens=4000
        )


@pytest.mark.asyncio
async def test_structured_call_with_no_text_block_raises():
    msgs = _FakeMessages(reply=_message(THINKING))
    with pytest.raises(RuntimeError, match="no JSON"):
        await claude_calls.structured_call(
            _client(msgs), system="s", content="b", tool=TOOL, max_tokens=10
        )


@pytest.mark.asyncio
async def test_stream_text_yields_deltas_with_the_shared_options():
    msgs = _FakeMessages(reply=_message(_text("Hello world")), deltas=["Hello ", "world"])
    out = [
        t async for t in claude_calls.stream_text(
            _client(msgs), system="SYS", user="brief", max_tokens=2000
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
            _client(msgs), system="s", user="b", max_tokens=10
        )
    ]
    assert msgs.calls[0]["timeout"].read == settings.ai_stream_read_timeout_s


@pytest.mark.asyncio
async def test_stream_text_hitting_the_cap_raises_after_the_text():
    msgs = _FakeMessages(reply=_message(_text("cut"), stop_reason="max_tokens"), deltas=["cut"])
    seen: list[str] = []
    with pytest.raises(RuntimeError, match="2000-token cap"):
        async for t in claude_calls.stream_text(
            _client(msgs), system="s", user="b", max_tokens=2000
        ):
            seen.append(t)
    assert seen == ["cut"]


@pytest.mark.asyncio
async def test_stream_text_refusal_raises_after_the_partial_text():
    msgs = _FakeMessages(reply=_message(stop_reason="refusal"), deltas=["partial"])
    seen: list[str] = []
    with pytest.raises(ModelDeclined):
        async for t in claude_calls.stream_text(
            _client(msgs), system="s", user="b", max_tokens=10
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
