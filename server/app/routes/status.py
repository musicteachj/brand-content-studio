"""Public status: is live AI available right now? No auth; cached in process for 30 s."""
from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, Depends, Response
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.config import settings
from app.database import get_database
from app.services.ai_ledger import budget_snapshot
from app.services.ai_pricing import usd_to_micros

router = APIRouter()

CACHE_SECONDS = 30
# About one text post: below this much room left today, say paused rather than let a
# visitor start something that would be refused.
STATUS_MIN_ROOM_MICROS = 60_000


class StatusResponse(BaseModel):
    live_ai_available: bool
    live_ai_reason: Literal["available", "off", "paused"]


_cache: tuple[float, StatusResponse] | None = None


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
        return _cache[1]
    if usd_to_micros(settings.ai_monthly_budget_usd) == 0:
        result = StatusResponse(live_ai_available=False, live_ai_reason="off")
    else:
        snap = await budget_snapshot(db)
        if snap.allowance_today - snap.spent_today >= STATUS_MIN_ROOM_MICROS:
            result = StatusResponse(live_ai_available=True, live_ai_reason="available")
        else:
            result = StatusResponse(live_ai_available=False, live_ai_reason="paused")
    _cache = (now, result)
    return result
