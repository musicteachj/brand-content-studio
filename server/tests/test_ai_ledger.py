import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import anyio
import pytest

from app.config import settings
from app.services.ai_ledger import (
    LineRequest,
    allowance_micros,
    budget_snapshot,
    delete_visitor,
    prune_closed,
    reserve,
    settle,
    sweep_stale,
)
from app.utils.errors import BudgetRefusal

NOV19 = datetime(2026, 11, 19, 15, tzinfo=UTC)


def _req(m: int) -> LineRequest:
    return LineRequest("anthropic", "claude-sonnet-5-5", "test", m)


async def _day_total(db, day="2026-11-19"):
    doc = await db.ai_spend_days.find_one({"_id": day})
    return doc["total_micros"] if doc else None


@pytest.mark.parametrize(
    "spent_before, days_left, expected",
    [(0, 30, 1_000_000), (4_000_000, 12, 1_500_000), (9_800_000, 12, 200_000), (8_000_000, 20, 500_000)],
)
def test_allowance_follows_the_pacing_formula(spent_before, days_left, expected):
    assert (
        allowance_micros(
            budget=10_000_000,
            spent_before_today=spent_before,
            days_left=days_left,
            multiplier=Decimal(3),
            floor=500_000,
        )
        == expected
    )


async def test_reserve_admits_up_to_todays_allowance_then_refuses(test_db):  # 3 x 10 / 12 = $2.50
    await reserve(test_db, [_req(1_000_000)], visitor_id=None, now=NOV19)
    await reserve(test_db, [_req(1_000_000)], visitor_id=None, now=NOV19)
    with pytest.raises(BudgetRefusal) as refused:
        await reserve(test_db, [_req(1_000_000)], visitor_id=None, now=NOV19)
    assert refused.value.code == "live_ai_paused"
    assert (await test_db.ai_spend_days.find_one({"_id": "2026-11-19"}))["total_micros"] == 2_000_000


async def test_reserve_writes_one_open_call_per_request(test_db):
    lines = await reserve(test_db, [_req(1_000), _req(2_000)], visitor_id="v", now=NOV19)
    assert [line.reserved_micros for line in lines] == [1_000, 2_000]
    assert {line.day for line in lines} == {"2026-11-19"}
    docs = await test_db.ai_spend_calls.find({}).to_list(None)
    assert len(docs) == 2 and all(d["status"] == "open" and d["month"] == "2026-11" for d in docs)
    assert await _day_total(test_db) == 3_000


async def test_spend_before_today_lowers_todays_allowance(test_db):
    await test_db.ai_spend_days.insert_one({"_id": "2026-11-05", "month": "2026-11", "total_micros": 4_000_000})
    # left 6M, 3 x 6M / 12 = 1.5M; 1.4M fits, then 200k does not.
    await reserve(test_db, [_req(1_400_000)], visitor_id=None, now=NOV19)
    with pytest.raises(BudgetRefusal):
        await reserve(test_db, [_req(200_000)], visitor_id=None, now=NOV19)


async def test_a_new_utc_month_starts_with_the_full_budget(test_db):
    await test_db.ai_spend_days.insert_one({"_id": "2026-11-19", "month": "2026-11", "total_micros": 9_900_000})
    dec1 = datetime(2026, 12, 1, 0, 5, tzinfo=UTC)
    await reserve(test_db, [_req(900_000)], visitor_id=None, now=dec1)  # 3 x 10 / 31
    assert await _day_total(test_db, "2026-12-01") == 900_000


async def test_the_month_is_never_exceeded(test_db):
    await test_db.ai_spend_days.insert_one({"_id": "2026-11-05", "month": "2026-11", "total_micros": 9_950_000})
    with pytest.raises(BudgetRefusal) as refused:
        await reserve(test_db, [_req(60_000)], visitor_id=None, now=NOV19)
    assert refused.value.reason == "month"
    await reserve(test_db, [_req(50_000)], visitor_id=None, now=NOV19)


async def test_visitor_with_room_left_is_admitted_once_more_then_refused(test_db):
    await reserve(test_db, [_req(100_000)], visitor_id="s1", now=NOV19)
    await reserve(test_db, [_req(60_000)], visitor_id="s1", now=NOV19)  # room was left: admitted
    with pytest.raises(BudgetRefusal) as refused:
        await reserve(test_db, [_req(1_000)], visitor_id="s1", now=NOV19)
    assert refused.value.code == "visitor_allowance"
    assert await _day_total(test_db) == 160_000
    # The refusal did not move the day total.
    await reserve(test_db, [_req(1)], visitor_id=None, now=NOV19)
    assert await _day_total(test_db) == 160_001


async def test_concurrent_reservations_cannot_overshoot_the_visitor_allowance(test_db):
    results = await asyncio.gather(
        *(reserve(test_db, [_req(40_000)], visitor_id="s2", now=NOV19) for _ in range(10)),
        return_exceptions=True,
    )
    assert sum(not isinstance(r, BudgetRefusal) for r in results) == 4
    assert (await test_db.ai_spend_visitors.find_one({"_id": "s2"}))["total_micros"] == 160_000
    assert await _day_total(test_db) == 160_000


async def test_concurrent_reservations_cannot_overshoot_the_day(test_db):
    results = await asyncio.gather(
        *(reserve(test_db, [_req(400_000)], visitor_id=None, now=NOV19) for _ in range(10)),
        return_exceptions=True,
    )
    assert sum(not isinstance(r, BudgetRefusal) for r in results) == 6
    assert await _day_total(test_db) == 2_400_000


async def test_a_day_refusal_gives_the_visitor_their_room_back(test_db):
    with pytest.raises(BudgetRefusal):
        await reserve(test_db, [_req(3_000_000)], visitor_id="s5", now=NOV19)
    assert (await test_db.ai_spend_visitors.find_one({"_id": "s5"}))["total_micros"] == 0
    assert await _day_total(test_db) is None


async def test_a_failed_call_insert_compensates_both_counters(test_db, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("insert failed")

    monkeypatch.setattr(test_db.ai_spend_calls.__class__, "insert_many", boom)
    with pytest.raises(RuntimeError):
        await reserve(test_db, [_req(50_000)], visitor_id="s6", now=NOV19)
    assert await _day_total(test_db) == 0
    assert (await test_db.ai_spend_visitors.find_one({"_id": "s6"}))["total_micros"] == 0


async def test_settle_moves_every_total_to_the_actual_cost(test_db):
    (line,) = await reserve(test_db, [_req(56_000)], visitor_id="s3", now=NOV19)
    assert await settle(test_db, line, actual_micros=4_000, outcome="ok", now=NOV19) is True
    assert await _day_total(test_db) == 4_000
    assert (await test_db.ai_spend_visitors.find_one({"_id": "s3"}))["total_micros"] == 4_000
    doc = await test_db.ai_spend_calls.find_one({"_id": line.id})
    assert doc["status"] == "settled" and doc["actual_micros"] == 4_000 and doc["outcome"] == "ok"


async def test_settle_is_idempotent(test_db):
    (line,) = await reserve(test_db, [_req(56_000)], visitor_id="s3", now=NOV19)
    assert await settle(test_db, line, actual_micros=4_000, outcome="ok", now=NOV19) is True
    assert await settle(test_db, line, actual_micros=0, outcome="again", now=NOV19) is False
    assert await _day_total(test_db) == 4_000


async def test_settle_tolerates_a_cleaned_up_visitor(test_db):
    (line,) = await reserve(test_db, [_req(56_000)], visitor_id="gone", now=NOV19)
    await delete_visitor(test_db, "gone")
    assert await settle(test_db, line, actual_micros=0, outcome="ok", now=NOV19) is True
    assert await test_db.ai_spend_visitors.find_one({"_id": "gone"}) is None
    assert await _day_total(test_db) == 0


async def test_settle_after_midnight_goes_to_the_reservation_day(test_db):
    late = datetime(2026, 11, 19, 23, 59, 50, tzinfo=UTC)
    (line,) = await reserve(test_db, [_req(100_000)], visitor_id=None, now=late)
    await settle(test_db, line, actual_micros=40_000, outcome="ok", now=late + timedelta(seconds=40))
    assert await _day_total(test_db) == 40_000
    assert await test_db.ai_spend_days.find_one({"_id": "2026-11-20"}) is None


async def test_the_sweeper_charges_reservations_older_than_ten_minutes(test_db):
    t = NOV19
    await reserve(test_db, [_req(10_000)], visitor_id=None, now=t)
    await reserve(test_db, [_req(20_000)], visitor_id=None, now=t + timedelta(minutes=9))
    assert await sweep_stale(test_db, now=t + timedelta(minutes=11)) == 1
    statuses = sorted([d["status"] async for d in test_db.ai_spend_calls.find({})])
    assert statuses == ["open", "swept"]
    assert await _day_total(test_db) == 30_000


async def test_settle_after_a_sweep_changes_nothing(test_db):
    (line,) = await reserve(test_db, [_req(10_000)], visitor_id=None, now=NOV19)
    await sweep_stale(test_db, now=NOV19 + timedelta(minutes=11))
    assert await settle(test_db, line, actual_micros=0, outcome="late", now=NOV19) is False
    assert await _day_total(test_db) == 10_000


async def test_prune_removes_closed_calls_older_than_35_days_only(test_db):
    old = NOV19 - timedelta(days=40)
    (a,) = await reserve(test_db, [_req(1_000)], visitor_id=None, now=old)
    (b,) = await reserve(test_db, [_req(1_000)], visitor_id=None, now=old)
    (c,) = await reserve(test_db, [_req(1_000)], visitor_id=None, now=NOV19 - timedelta(days=2))
    await settle(test_db, a, actual_micros=500, outcome="ok", now=old)
    # b stays open (not closed), c is recent.
    await settle(test_db, c, actual_micros=500, outcome="ok", now=NOV19)
    assert await prune_closed(test_db, now=NOV19) == 1
    remaining = {d["_id"] async for d in test_db.ai_spend_calls.find({})}
    assert remaining == {b.id, c.id}
    assert await test_db.ai_spend_days.count_documents({}) == 2  # day totals are never pruned


async def test_a_zero_budget_refuses_without_touching_the_database(monkeypatch):
    monkeypatch.setattr(settings, "ai_monthly_budget_usd", Decimal(0))

    class NoDb:
        def __getattr__(self, name):
            raise AssertionError(f"database touched: {name}")

    with pytest.raises(BudgetRefusal) as refused:
        await reserve(NoDb(), [_req(1)], visitor_id="x", now=NOV19)
    assert refused.value.reason == "off" and refused.value.code == "live_ai_paused"


@pytest.mark.parametrize("cap", [Decimal(0), Decimal(-1)])
async def test_a_visitor_cap_of_zero_or_less_refuses_a_new_visitor_and_writes_nothing(
    test_db, monkeypatch, cap
):
    monkeypatch.setattr(settings, "ai_visitor_budget_usd", cap)
    with pytest.raises(BudgetRefusal) as refused:
        await reserve(test_db, [_req(1)], visitor_id="fresh", now=NOV19)
    assert refused.value.reason == "visitor"
    assert await test_db.ai_spend_visitors.count_documents({}) == 0
    assert await test_db.ai_spend_days.count_documents({}) == 0


async def test_a_positive_visitor_cap_still_admits_a_new_visitors_first_call(test_db, monkeypatch):
    monkeypatch.setattr(settings, "ai_visitor_budget_usd", Decimal("0.01"))
    await reserve(test_db, [_req(1)], visitor_id="fresh", now=NOV19)
    assert (await test_db.ai_spend_visitors.find_one({"_id": "fresh"}))["total_micros"] == 1


async def test_budget_snapshot(test_db):
    await test_db.ai_spend_days.insert_one({"_id": "2026-11-05", "month": "2026-11", "total_micros": 4_000_000})
    await reserve(test_db, [_req(100_000)], visitor_id=None, now=NOV19)
    snap = await budget_snapshot(test_db, now=NOV19)
    assert snap.allowance_today == 1_500_000
    assert snap.spent_today == 100_000
    assert snap.left_this_month == 6_000_000


async def test_a_cancel_during_the_call_insert_leaves_counters_and_documents_consistent(
    test_db, monkeypatch
):
    original = test_db.ai_spend_calls.__class__.insert_many

    async def slow_insert(self, *args, **kwargs):
        await anyio.sleep(0.3)
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(test_db.ai_spend_calls.__class__, "insert_many", slow_insert)
    with anyio.move_on_after(0.1):
        await reserve(test_db, [_req(50_000)], visitor_id="s7", now=NOV19)
    docs = await test_db.ai_spend_calls.count_documents({})
    day = await _day_total(test_db) or 0
    visitor = (await test_db.ai_spend_visitors.find_one({"_id": "s7"}) or {}).get("total_micros", 0)
    # Either the reservation fully landed with its call document, or both counters are zero.
    assert (docs, day, visitor) in {(1, 50_000, 50_000), (0, 0, 0)}
    assert (docs, day, visitor) == (1, 50_000, 50_000)  # the shield lets the write finish


async def test_a_cancel_during_settle_does_not_split_the_flip_and_the_totals(test_db, monkeypatch):
    (line,) = await reserve(test_db, [_req(56_000)], visitor_id="s8", now=NOV19)
    original = test_db.ai_spend_days.__class__.update_one

    async def slow_update(self, *args, **kwargs):
        await anyio.sleep(0.3)
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(test_db.ai_spend_days.__class__, "update_one", slow_update)
    with anyio.move_on_after(0.1):
        await settle(test_db, line, actual_micros=4_000, outcome="ok", now=NOV19)
    monkeypatch.undo()
    assert (await test_db.ai_spend_calls.find_one({"_id": line.id}))["status"] == "settled"
    assert await _day_total(test_db) == 4_000
    assert (await test_db.ai_spend_visitors.find_one({"_id": "s8"}))["total_micros"] == 4_000
