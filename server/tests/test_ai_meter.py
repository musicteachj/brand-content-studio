import json

import anyio

from app.config import settings
from app.services.ai_ledger import LineRequest
from app.services.ai_meter import claude_line, embedding_line, reserve_action
from app.services.ai_pricing import (
    IMAGE_TOKEN_BOUND,
    SCHEMA_OVERHEAD_TOKENS,
    claude_reservation_micros,
    estimate_tokens,
)


def _req(m: int) -> LineRequest:
    return LineRequest("anthropic", "claude-sonnet-5-5", "test", m)


async def _call(db, line):
    return await db.ai_spend_calls.find_one({"_id": line.reserved.id})


async def test_finalize_releases_lines_that_never_started(test_db):
    action = await reserve_action(test_db, [_req(50_000)], visitor_id=None)
    async with action:
        pass
    doc = await _call(test_db, action.lines[0])
    assert doc["actual_micros"] == 0 and doc["outcome"] == "not_attempted"


async def test_finalize_keeps_a_started_unsettled_line_at_its_reservation(test_db):
    action = await reserve_action(test_db, [_req(50_000)], visitor_id=None)
    async with action:
        action.lines[0].mark_started()
    doc = await _call(test_db, action.lines[0])
    assert doc["actual_micros"] == 50_000 and doc["outcome"] == "canceled_or_unknown"


async def test_finalize_still_settles_when_the_task_is_canceled(test_db):
    action = await reserve_action(test_db, [_req(50_000)], visitor_id=None)
    with anyio.CancelScope() as scope:
        async with action:
            action.lines[0].mark_started()
            scope.cancel()
            await anyio.sleep(1)
    doc = await _call(test_db, action.lines[0])
    assert doc["status"] == "settled" and doc["actual_micros"] == 50_000


async def test_settle_usage_prices_the_usage_and_later_settles_are_no_ops(test_db):
    action = await reserve_action(test_db, [_req(56_000)], visitor_id=None)
    line = action.lines[0]
    line.mark_started()
    await line.settle_usage(model="claude-sonnet-5-5", input_tokens=1_000, output_tokens=200)
    assert line.settled
    await line.settle_unbilled("rate_limited")
    await action.finalize()
    doc = await _call(test_db, line)
    assert doc["actual_micros"] == 4_000 and doc["outcome"] == "ok"


async def test_settle_unbilled_and_settle_reserved_and_tokens(test_db):
    action = await reserve_action(
        test_db,
        [_req(50_000), _req(50_000), LineRequest("openai", "text-embedding-3-small", "embed", 20)],
        visitor_id=None,
    )
    a, b, c = action.lines
    await a.settle_unbilled("rejected")
    await b.settle_reserved("timeout")
    await c.settle_tokens(6_000)
    assert (await _call(test_db, a))["actual_micros"] == 0
    assert (await _call(test_db, b))["actual_micros"] == 50_000
    assert (await _call(test_db, c))["actual_micros"] == 120
    assert a.settled and b.settled and c.settled


def test_claude_line_counts_text_images_schema_and_extra():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    line = claude_line(
        "post",
        system="s" * 1_000,
        content=[
            {"type": "text", "text": "t" * 1_000},
            {"type": "image", "source": {"type": "base64", "data": "AAAA"}},
        ],
        max_tokens=1_000,
        schema=schema,
        extra_input_tokens=2_000,
    )
    expected_in = (
        1_000 + IMAGE_TOKEN_BOUND + estimate_tokens(json.dumps(schema)) + SCHEMA_OVERHEAD_TOKENS + 2_000
    )
    assert line.model == settings.ai_model and line.provider == "anthropic" and line.purpose == "post"
    assert line.reserved_micros == claude_reservation_micros(
        settings.ai_model, input_tokens=expected_in, max_tokens=1_000
    )


def test_claude_line_accepts_plain_string_content():
    line = claude_line("p", system="", content="x" * 2_000, max_tokens=10)
    assert line.reserved_micros == claude_reservation_micros(
        settings.ai_model, input_tokens=1_000, max_tokens=10
    )


def test_embedding_line():
    line = embedding_line("embed", ["x" * 2_000])
    assert line.provider == "openai" and line.model == settings.embedding_model
    assert line.reserved_micros == 20


async def test_reserve_action_passes_the_visitor_through(test_db):
    action = await reserve_action(test_db, [_req(1_000)], visitor_id="vv")
    assert action.lines[0].reserved.visitor_id == "vv"
    assert (await test_db.ai_spend_visitors.find_one({"_id": "vv"}))["total_micros"] == 1_000
