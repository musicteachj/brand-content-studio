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
from app.services.ai_pricing import claude_reservation_micros, usd_to_micros
from app.services.ai_service import (
    CARD_COPY_MAX_TOKENS,
    CARD_FIELDS_MAX_TOKENS,
    DOC_COPY_MAX_TOKENS,
    DOC_SECTIONS_MAX_TOKENS,
    MAX_TOKENS,
    TEMPLATE_FILL_MAX_TOKENS,
)

router = APIRouter()

CACHE_SECONDS = 30
# Below the largest generation's reservation left today, say paused rather than let a
# visitor start something that would be refused. Every action reserves all of its calls up
# front, so the largest generation is two calls with 8,000 output tokens between them (a
# document, or a LinkedIn post and its card). 21,000 input tokens covers both prompts at
# their worst on the demo corpus: a 2,000-character brief of 4-byte characters, the 10
# pinned voice and pillar chunks plus the 6 largest others, and the first call's output fed
# to the second (a LinkedIn post then reserves 121,060; test_status.py builds it with the
# real prompt and line helpers). On Sonnet 5.5 that comes to $0.122. Filling a template
# from an uploaded file is sized by that file, so a long one can still be refused; its
# refusal points at the examples like any other.
LARGEST_ACTION_OUTPUT_TOKENS = max(
    MAX_TOKENS,
    TEMPLATE_FILL_MAX_TOKENS,
    CARD_COPY_MAX_TOKENS + CARD_FIELDS_MAX_TOKENS,
    MAX_TOKENS + CARD_FIELDS_MAX_TOKENS,
    DOC_COPY_MAX_TOKENS + DOC_SECTIONS_MAX_TOKENS,
)
LARGEST_ACTION_INPUT_TOKENS = 21_000


def status_min_room_micros() -> int:
    """The room live AI needs today before status says available, at the configured model's
    price."""
    return claude_reservation_micros(
        settings.ai_model,
        input_tokens=LARGEST_ACTION_INPUT_TOKENS,
        max_tokens=LARGEST_ACTION_OUTPUT_TOKENS,
    )


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
    if snap.allowance_today - snap.spent_today >= status_min_room_micros():
        return "available"
    return "paused"
