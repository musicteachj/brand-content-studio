"""Public status: is live AI available right now, and how does a visitor get in? No auth;
the live-AI answer is cached in process for 30 s."""
from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, Depends, Response
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.config import settings, turnstile_keys
from app.database import get_database
from app.services.ai_ledger import budget_snapshot
from app.services.ai_pricing import usd_to_micros

router = APIRouter()

CACHE_SECONDS = 30
# About one text post: below this much room left today, say paused rather than let a
# visitor start something that would be refused.
STATUS_MIN_ROOM_MICROS = 60_000


LiveReason = Literal["available", "off", "paused"]


class StatusResponse(BaseModel):
    live_ai_available: bool
    live_ai_reason: LiveReason
    # The Turnstile site key the demo start's widget uses (Cloudflare's always-pass test
    # key in development with blank keys), and whether password sign-in is open.
    turnstile_site_key: str
    password_login: bool


_cache: tuple[float, LiveReason] | None = None


def clear_status_cache() -> None:
    global _cache
    _cache = None


@router.get("", response_model=StatusResponse)
async def get_status(
    response: Response, db: AsyncIOMotorDatabase = Depends(get_database)
) -> StatusResponse:
    global _cache
    response.headers["Cache-Control"] = f"public, max-age={CACHE_SECONDS}"
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < CACHE_SECONDS:
        reason = _cache[1]
    else:
        reason = await _live_reason(db)
        _cache = (now, reason)
    return StatusResponse(
        live_ai_available=reason == "available",
        live_ai_reason=reason,
        turnstile_site_key=turnstile_keys(settings)[0],
        password_login=settings.environment != "production",
    )


async def _live_reason(db: AsyncIOMotorDatabase) -> LiveReason:
    if usd_to_micros(settings.ai_monthly_budget_usd) == 0:
        return "off"
    snap = await budget_snapshot(db)
    if snap.allowance_today - snap.spent_today >= STATUS_MIN_ROOM_MICROS:
        return "available"
    return "paused"
