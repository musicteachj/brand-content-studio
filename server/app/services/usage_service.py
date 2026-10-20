"""The demo account's daily AI-call counter (known-gaps plan, step 1).

One document per account per UTC day in `usage`:
`{_id: "<user_id>:<YYYY-MM-DD>", user_id, day, count, expires_at}`. Every paid
model route consumes one unit when the request is admitted, so routes that save
nothing (brand extract, template AI fill, fill from a document) are capped too.
A TTL index on `expires_at` removes old days.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.models.common import utcnow

# Kept a day past its own day, then the TTL monitor drops it.
_RETAIN = timedelta(days=2)


async def consume_demo_ai_action(
    db: AsyncIOMotorDatabase, user_id: str, limit: int, now: datetime | None = None
) -> bool:
    """Take one unit of today's allowance; False when it's used up. The check and
    the increment are one conditional write, so concurrent requests can't
    overshoot the limit."""
    if limit <= 0:
        return False
    now = now or utcnow()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day = start.strftime("%Y-%m-%d")
    query = {"_id": f"{user_id}:{day}", "count": {"$lt": limit}}
    inc = {"$inc": {"count": 1}}
    try:
        await db.usage.update_one(
            query,
            {**inc, "$setOnInsert": {"user_id": ObjectId(user_id), "day": day, "expires_at": start + _RETAIN}},
            upsert=True,
        )
        return True
    except DuplicateKeyError:
        # The day's document exists, and either it's at the limit or another
        # request created it first. A plain conditional update tells them apart.
        result = await db.usage.update_one(query, inc)
        return result.modified_count == 1
