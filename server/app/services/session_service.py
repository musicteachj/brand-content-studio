"""Visitor demo sessions: each demo start gets its own 24-hour session, whose ID rides in
the token (`sid`). The ID scopes the visitor's AI allowance in the ledger; the hourly
cleanup job removes expired sessions and what they made."""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

SESSION_TTL = timedelta(hours=24)


async def create_session(
    db: AsyncIOMotorDatabase, *, user_id: ObjectId, now: datetime | None = None
) -> dict[str, Any]:
    created = now or datetime.now(timezone.utc)
    doc: dict[str, Any] = {
        "_id": secrets.token_urlsafe(32),
        "user_id": user_id,
        "created_at": created,
        "expires_at": created + SESSION_TTL,
    }
    await db.demo_sessions.insert_one(doc)
    return doc


async def get_active_session(
    db: AsyncIOMotorDatabase, session_id: str, *, now: datetime | None = None
) -> dict[str, Any] | None:
    """The session if it exists and has not expired, else None."""
    current = now or datetime.now(timezone.utc)
    doc: dict[str, Any] | None = await db.demo_sessions.find_one(
        {"_id": session_id, "expires_at": {"$gt": current}}
    )
    return doc


async def end_session(
    db: AsyncIOMotorDatabase, session_id: str, *, now: datetime | None = None
) -> None:
    """End a session now. The document stays, expired: the hourly cleanup removes it, its
    spend allowance, and the visitor's generations (which keep their own `expires_at`)."""
    current = now or datetime.now(timezone.utc)
    await db.demo_sessions.update_one(
        {"_id": session_id, "expires_at": {"$gt": current}}, {"$set": {"expires_at": current}}
    )
