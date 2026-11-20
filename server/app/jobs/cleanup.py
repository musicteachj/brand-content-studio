"""Hourly cleanup, run as `python -m app.jobs.cleanup` by a scheduled task.

Sweeps stale open AI reservations and prunes old closed call documents. Exits 1 on any
exception so the scheduled-task alarm fires.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings
from app.services.ai_ledger import prune_closed, sweep_stale

logger = logging.getLogger("app.jobs.cleanup")


async def run_cleanup(db: AsyncIOMotorDatabase, *, now: datetime | None = None) -> dict[str, int]:
    swept = await sweep_stale(db, now=now)
    pruned = await prune_closed(db, now=now)
    return {"swept": swept, "pruned": pruned}


async def _run() -> dict[str, int]:
    client: AsyncIOMotorClient = AsyncIOMotorClient(
        settings.mongodb_url.get_secret_value(), maxPoolSize=2
    )
    try:
        return await run_cleanup(client[settings.database_name])
    finally:
        client.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        counts = asyncio.run(_run())
    except Exception:
        logger.exception("cleanup failed")
        sys.exit(1)
    logger.info("cleanup: swept=%d pruned=%d", counts["swept"], counts["pruned"])


if __name__ == "__main__":
    main()
