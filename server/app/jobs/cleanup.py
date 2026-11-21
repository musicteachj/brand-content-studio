"""Hourly cleanup, run as `python -m app.jobs.cleanup` by a scheduled task.

Sweeps stale open AI reservations, prunes old closed call documents, removes expired
visitor work (each generation's files first, then its record), removes document folders
older than a day that no record points at, and removes expired visitor sessions with their
running spend totals (the ledger's day totals are never touched). Exits 1 on any exception
so the scheduled-task alarm fires; a generation whose files couldn't be removed keeps its
record, so the next run tries it again.

Keep this import chain free of chromadb (a test checks it): the job runs in its own small
process and touches only Mongo and file storage.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timedelta

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings
from app.models.common import utcnow
from app.services.ai_ledger import delete_visitor, prune_closed, sweep_stale
from app.services.storage_service import build_document_prefix, get_storage

logger = logging.getLogger("app.jobs.cleanup")


async def remove_expired_generations(db: AsyncIOMotorDatabase, *, now: datetime) -> int:
    """Delete each expired visitor generation's built files, then the records whose files
    are gone. Examples and the owner's work carry no expiry and are never touched. Raises
    after the rest is done when any files couldn't be removed; those records stay."""
    storage = get_storage()
    removed: list[ObjectId] = []
    failed = 0
    cursor = db.generations.find(
        {
            "expires_at": {"$lte": now},
            "session_id": {"$exists": True},
            "is_example": {"$ne": True},
        },
        projection={"_id": 1, "workspace_id": 1},
    )
    async for doc in cursor:
        prefix = build_document_prefix(str(doc["workspace_id"]), str(doc["_id"]))
        try:
            await storage.delete_prefix(prefix, strict=True)
        except Exception:  # noqa: BLE001
            logger.exception("Couldn't remove the files for expired generation %s", doc["_id"])
            failed += 1
            continue
        removed.append(doc["_id"])
    if removed:
        await db.generations.delete_many({"_id": {"$in": removed}})
    if failed:
        raise RuntimeError(
            f"Couldn't remove the files for {failed} expired generations; "
            "their records are kept for the next run"
        )
    return len(removed)


# A document's files are saved before its record, seconds apart; a folder this old with no
# record is left over from a request that died in between (or a delete that couldn't remove
# its files), never one still being written.
ORPHAN_AGE = timedelta(hours=24)


async def remove_orphaned_documents(db: AsyncIOMotorDatabase, *, now: datetime) -> int:
    """Delete document folders older than ORPHAN_AGE whose generation has no record. A
    folder whose name isn't a generation id is left alone. Raises after the rest is done
    when any folder couldn't be removed."""
    storage = get_storage()
    by_id: dict[ObjectId, str] = {}
    for prefix in await storage.document_prefixes_before(now - ORPHAN_AGE):
        name = prefix.rsplit("/", 1)[-1]
        if ObjectId.is_valid(name):
            by_id[ObjectId(name)] = prefix
    if not by_id:
        return 0
    known = {
        doc["_id"]
        async for doc in db.generations.find({"_id": {"$in": list(by_id)}}, projection={"_id": 1})
    }
    removed = 0
    failed = 0
    for oid, prefix in by_id.items():
        if oid in known:
            continue
        try:
            await storage.delete_prefix(prefix, strict=True)
        except Exception:  # noqa: BLE001
            logger.exception("Couldn't remove the orphaned document folder %s", prefix)
            failed += 1
            continue
        removed += 1
    if failed:
        raise RuntimeError(f"Couldn't remove {failed} orphaned document folders")
    return removed


async def remove_expired_sessions(db: AsyncIOMotorDatabase, *, now: datetime) -> int:
    """Delete expired visitor sessions and their running spend totals. The total goes
    first, so a crash between the two leaves an expired session the next run removes."""
    removed = 0
    async for session in db.demo_sessions.find({"expires_at": {"$lte": now}}, projection={"_id": 1}):
        await delete_visitor(db, session["_id"])
        result = await db.demo_sessions.delete_one({"_id": session["_id"]})
        removed += int(result.deleted_count)
    return removed


async def run_cleanup(db: AsyncIOMotorDatabase, *, now: datetime | None = None) -> dict[str, int]:
    current = now or utcnow()
    swept = await sweep_stale(db, now=current)
    pruned = await prune_closed(db, now=current)
    file_error: Exception | None = None
    expired_generations = orphaned_documents = 0
    try:
        expired_generations = await remove_expired_generations(db, now=current)
    except RuntimeError as exc:
        # Sessions still go this run; the kept generations carry their own expiry.
        file_error = exc
    try:
        orphaned_documents = await remove_orphaned_documents(db, now=current)
    except Exception as exc:  # noqa: BLE001 (sessions still go; the run fails after)
        logger.exception("The orphaned document sweep failed")
        file_error = file_error or exc
    expired_sessions = await remove_expired_sessions(db, now=current)
    if file_error is not None:
        raise file_error
    return {
        "swept": swept,
        "pruned": pruned,
        "expired_generations": expired_generations,
        "orphaned_documents": orphaned_documents,
        "expired_sessions": expired_sessions,
    }


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
    logger.info(
        "cleanup: swept=%d pruned=%d expired_generations=%d orphaned_documents=%d "
        "expired_sessions=%d",
        counts["swept"],
        counts["pruned"],
        counts["expired_generations"],
        counts["orphaned_documents"],
        counts["expired_sessions"],
    )


if __name__ == "__main__":
    main()
