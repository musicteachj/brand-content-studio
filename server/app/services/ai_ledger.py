"""The AI dollar ledger: reserve before a model call, settle after, sweep what's left.

Three collections, integer micro-dollars, never a TTL on spend:
- `ai_spend_days {_id: "YYYY-MM-DD", month, total_micros}`: settled + open spend per UTC day.
- `ai_spend_calls {_id, day, month, visitor_id, provider, model, purpose, reserved_micros,
  actual_micros|null, status: open|settled|swept, outcome, created_at, settled_at}`.
- `ai_spend_visitors {_id: visitor_id, total_micros}`: one demo session's spend.

Atomicity needs no lock: each counter moves by one conditional `$inc` (an upsert, with a
plain conditional update after a lost creation race), so concurrent requests cannot overshoot. Pacing (UTC):
`allowance_today = min(left, max(multiplier x left / days_left, floor))`, where `left` is the
month's budget less everything dated before today. The month is never exceeded.
"""
from __future__ import annotations

import logging
from calendar import monthrange
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_CEILING, Decimal
from typing import Any, Literal

import anyio
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.config import settings
from app.models.common import utcnow
from app.services.ai_pricing import usd_to_micros
from app.utils.errors import BudgetRefusal

logger = logging.getLogger(__name__)

STALE_AFTER = timedelta(minutes=10)


@dataclass(frozen=True)
class LineRequest:
    provider: Literal["anthropic", "openai"]
    model: str
    purpose: str
    reserved_micros: int


@dataclass(frozen=True)
class ReservedLine:
    id: ObjectId
    day: str
    visitor_id: str | None
    provider: str
    model: str
    purpose: str
    reserved_micros: int


@dataclass(frozen=True)
class BudgetSnapshot:
    allowance_today: int
    spent_today: int
    left_this_month: int


def allowance_micros(
    *, budget: int, spent_before_today: int, days_left: int, multiplier: Decimal, floor: int
) -> int:
    left = max(budget - spent_before_today, 0)
    paced = (multiplier * left / max(days_left, 1)).to_integral_value(rounding=ROUND_CEILING)
    return min(left, max(int(paced), floor))


async def _conditional_inc(
    collection: Any,
    query: Mapping[str, Any],
    amount: int,
    *,
    set_on_insert: Mapping[str, Any] | None = None,
) -> bool:
    """Add `amount` to `total_micros` only where `query` matches; False when it didn't.
    The first write for a key creates the document (upsert), so a lost race on creation
    (DuplicateKeyError) falls back to a plain conditional update."""
    update: dict[str, Any] = {"$inc": {"total_micros": amount}}
    if set_on_insert:
        update["$setOnInsert"] = dict(set_on_insert)
    try:
        await collection.update_one(query, update, upsert=True)
        return True
    except DuplicateKeyError:
        result = await collection.update_one(query, {"$inc": {"total_micros": amount}})
        return bool(result.modified_count == 1)


def _month_context(now: datetime) -> tuple[str, str, int]:
    days_left = monthrange(now.year, now.month)[1] - now.day + 1
    return now.strftime("%Y-%m-%d"), now.strftime("%Y-%m"), days_left


async def _spent_before(db: AsyncIOMotorDatabase, month: str, day: str) -> int:
    cursor = db.ai_spend_days.aggregate(
        [
            {"$match": {"month": month, "_id": {"$lt": day}}},
            {"$group": {"_id": None, "total": {"$sum": "$total_micros"}}},
        ]
    )
    rows = await cursor.to_list(1)
    return int(rows[0]["total"]) if rows else 0


def _allowance(budget: int, spent_before: int, days_left: int) -> int:
    return allowance_micros(
        budget=budget,
        spent_before_today=spent_before,
        days_left=days_left,
        multiplier=settings.ai_pacing_multiplier,
        floor=usd_to_micros(settings.ai_daily_floor_usd),
    )


async def reserve(
    db: AsyncIOMotorDatabase,
    requests: Sequence[LineRequest],
    *,
    visitor_id: str | None,
    now: datetime | None = None,
) -> list[ReservedLine]:
    """Take the worst-case cost of `requests` from today's allowance (and the visitor's),
    or raise `BudgetRefusal`. Nothing here holds a lock across the model call."""
    budget = usd_to_micros(settings.ai_monthly_budget_usd)
    if budget == 0:
        raise BudgetRefusal("off")
    now = now or utcnow()
    amount = sum(r.reserved_micros for r in requests)
    day, month, days_left = _month_context(now)
    spent_before = await _spent_before(db, month, day)
    left = max(budget - spent_before, 0)
    allowance = _allowance(budget, spent_before, days_left)

    # Shielded: a cancellation between the first counter and the call documents would leave
    # a phantom charge with no document for the sweeper to find. Inside the shield the
    # sequence either completes (and the sweeper can later close the lines, so the worst
    # case is over-counted, which fails closed) or compensates both counters. No deadline:
    # a timeout here could abandon a half-applied sequence, which is the under-counted
    # direction; the Mongo driver's own timeouts bound each write.
    with anyio.CancelScope(shield=True):
        lines = await _write_reservation(db, requests, visitor_id, now, amount, allowance, left)
    return lines


async def _write_reservation(
    db: AsyncIOMotorDatabase,
    requests: Sequence[LineRequest],
    visitor_id: str | None,
    now: datetime,
    amount: int,
    allowance: int,
    left: int,
) -> list[ReservedLine]:
    day, month, _ = _month_context(now)
    if visitor_id:
        cap = usd_to_micros(settings.ai_visitor_budget_usd)
        # The upsert below inserts a new visitor's document whatever the filter says, so a
        # cap of 0 or less must refuse here, before any write.
        if cap <= 0:
            raise BudgetRefusal("visitor")
        # Shared rule (portfolio-infra/PLAN.md, 2026-11-19): admit while the visitor has room
        # left, counted at settled + open spend; one call may overshoot. The day check below
        # still reserves the worst case.
        if not await _conditional_inc(
            db.ai_spend_visitors, {"_id": visitor_id, "total_micros": {"$lt": cap}}, amount
        ):
            raise BudgetRefusal("visitor")

    if amount > allowance or not await _conditional_inc(
        db.ai_spend_days,
        {"_id": day, "total_micros": {"$lte": allowance - amount}},
        amount,
        set_on_insert={"month": month},
    ):
        if visitor_id:
            await db.ai_spend_visitors.update_one({"_id": visitor_id}, {"$inc": {"total_micros": -amount}})
        raise BudgetRefusal("month" if allowance >= left else "today")

    lines = [
        ReservedLine(
            id=ObjectId(),
            day=day,
            visitor_id=visitor_id,
            provider=r.provider,
            model=r.model,
            purpose=r.purpose,
            reserved_micros=r.reserved_micros,
        )
        for r in requests
    ]
    try:
        await db.ai_spend_calls.insert_many(
            [
                {
                    "_id": line.id,
                    "day": day,
                    "month": month,
                    "visitor_id": visitor_id,
                    "provider": line.provider,
                    "model": line.model,
                    "purpose": line.purpose,
                    "reserved_micros": line.reserved_micros,
                    "actual_micros": None,
                    "status": "open",
                    "outcome": None,
                    "created_at": now,
                    "settled_at": None,
                }
                for line in lines
            ]
        )
    except BaseException:
        await db.ai_spend_days.update_one({"_id": day}, {"$inc": {"total_micros": -amount}})
        if visitor_id:
            await db.ai_spend_visitors.update_one({"_id": visitor_id}, {"$inc": {"total_micros": -amount}})
        raise
    return lines


async def settle(
    db: AsyncIOMotorDatabase,
    line: ReservedLine,
    *,
    actual_micros: int,
    outcome: str,
    now: datetime | None = None,
) -> bool:
    """Close one open call at its real cost. False when it was already settled or swept.
    The adjustment goes to the reservation's day, even after midnight."""
    now = now or utcnow()
    # Shielded: the status flip and the totals adjustment must not be split by a cancellation,
    # or a settled call would keep its full reservation in the totals (over-counted).
    flipped = False
    with anyio.CancelScope(shield=True):
        matched = await db.ai_spend_calls.find_one_and_update(
            {"_id": line.id, "status": "open"},
            {"$set": {"status": "settled", "actual_micros": actual_micros, "outcome": outcome, "settled_at": now}},
        )
        if matched is not None:
            flipped = True
        delta = actual_micros - line.reserved_micros
        if flipped and delta:
            await db.ai_spend_days.update_one({"_id": line.day}, {"$inc": {"total_micros": delta}})
            if line.visitor_id:
                # No upsert: a cleaned-up session has no document, and that is fine.
                await db.ai_spend_visitors.update_one(
                    {"_id": line.visitor_id}, {"$inc": {"total_micros": delta}}
                )
    return flipped


async def sweep_stale(db: AsyncIOMotorDatabase, *, now: datetime | None = None) -> int:
    """Close open reservations older than `STALE_AFTER` at their reserved amount (the totals
    already hold it)."""
    now = now or utcnow()
    result = await db.ai_spend_calls.update_many(
        {"status": "open", "created_at": {"$lt": now - STALE_AFTER}},
        {"$set": {"status": "swept", "outcome": "swept", "settled_at": now}},
    )
    return int(result.modified_count)


async def prune_closed(
    db: AsyncIOMotorDatabase,
    *,
    now: datetime | None = None,
    older_than: timedelta = timedelta(days=35),
) -> int:
    """Delete closed call documents older than `older_than`. Day totals are never pruned."""
    now = now or utcnow()
    result = await db.ai_spend_calls.delete_many(
        {"status": {"$in": ["settled", "swept"]}, "created_at": {"$lt": now - older_than}}
    )
    return int(result.deleted_count)


async def budget_snapshot(db: AsyncIOMotorDatabase, *, now: datetime | None = None) -> BudgetSnapshot:
    now = now or utcnow()
    budget = usd_to_micros(settings.ai_monthly_budget_usd)
    day, month, days_left = _month_context(now)
    spent_before = await _spent_before(db, month, day)
    today = await db.ai_spend_days.find_one({"_id": day})
    return BudgetSnapshot(
        allowance_today=_allowance(budget, spent_before, days_left),
        spent_today=int(today["total_micros"]) if today else 0,
        left_this_month=max(budget - spent_before, 0),
    )


async def delete_visitor(db: AsyncIOMotorDatabase, visitor_id: str) -> None:
    """Forget one session's running total. Its spend stays in the day totals."""
    await db.ai_spend_visitors.delete_one({"_id": visitor_id})
