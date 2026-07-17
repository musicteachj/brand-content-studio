"""Asset records + workspace counter bookkeeping. The heavy lifting (parse →
chunk → embed → upsert) lives in `ingestion_service`; this module owns the
Mongo doc lifecycle and the denormalized counts on the workspace."""
from __future__ import annotations

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.asset import AssetKind, AssetResponse, IngestionStatus
from app.models.common import serialize_doc, utcnow


def _to_response(doc: dict) -> AssetResponse:
    return AssetResponse(**serialize_doc(doc))


async def create_asset(
    db: AsyncIOMotorDatabase,
    workspace_oid: ObjectId,
    *,
    asset_oid: ObjectId,
    filename: str,
    content_type: str,
    asset_kind: AssetKind,
    size_bytes: int,
    storage_key: str,
) -> dict:
    now = utcnow()
    doc = {
        "_id": asset_oid,
        "workspace_id": workspace_oid,
        "filename": filename,
        "content_type": content_type,
        "asset_kind": asset_kind.value,
        "storage_key": storage_key,
        "size_bytes": size_bytes,
        "ingestion_status": IngestionStatus.processing.value,
        "chunk_count": 0,
        "error": None,
        "ingested_at": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.assets.insert_one(doc)
    await db.workspaces.update_one(
        {"_id": workspace_oid}, {"$inc": {"asset_count": 1}, "$set": {"updated_at": now}}
    )
    return doc


async def list_assets(
    db: AsyncIOMotorDatabase, workspace_oid: ObjectId, *, limit: int = 30, offset: int = 0
) -> tuple[list[AssetResponse], int | None]:
    cursor = (
        db.assets.find({"workspace_id": workspace_oid})
        .sort("created_at", -1)
        .skip(offset)
        .limit(limit + 1)
    )
    docs = [doc async for doc in cursor]
    has_more = len(docs) > limit
    items = [_to_response(d) for d in docs[:limit]]
    return items, (offset + limit if has_more else None)


async def get_asset(
    db: AsyncIOMotorDatabase, workspace_oid: ObjectId, asset_id: str
) -> dict | None:
    try:
        oid = ObjectId(asset_id)
    except Exception:
        return None
    return await db.assets.find_one({"_id": oid, "workspace_id": workspace_oid})


async def asset_response(doc: dict) -> AssetResponse:
    return _to_response(doc)


async def mark_ready(
    db: AsyncIOMotorDatabase, asset_oid: ObjectId, chunk_count: int
) -> dict | None:
    """Flip an asset to ready and bump the workspace's retrievable-chunk count.

    Returns the asset doc, or None if the asset was deleted mid-ingest (the
    caller should then drop the just-upserted vectors to avoid an orphan)."""
    now = utcnow()
    doc = await db.assets.find_one_and_update(
        {"_id": asset_oid},
        {
            "$set": {
                "ingestion_status": IngestionStatus.ready.value,
                "chunk_count": chunk_count,
                "error": None,
                "ingested_at": now,
                "updated_at": now,
            }
        },
    )
    if doc:
        await db.workspaces.update_one(
            {"_id": doc["workspace_id"]},
            {"$inc": {"ready_chunk_count": chunk_count}, "$set": {"updated_at": now}},
        )
    return doc


async def mark_error(db: AsyncIOMotorDatabase, asset_oid: ObjectId, error: str) -> None:
    await db.assets.update_one(
        {"_id": asset_oid},
        {
            "$set": {
                "ingestion_status": IngestionStatus.error.value,
                "error": error[:500],
                "updated_at": utcnow(),
            }
        },
    )


async def mark_processing(db: AsyncIOMotorDatabase, asset_oid: ObjectId) -> dict | None:
    """Reset an asset to `processing` for a re-ingest: clear the error and, if it
    was `ready`, decrement the workspace's ready-chunk count (a fresh ingest will
    re-add the new count). Returns the updated asset doc, or None if it's gone."""
    now = utcnow()
    doc = await db.assets.find_one({"_id": asset_oid})
    if not doc:
        return None
    if doc.get("ingestion_status") == IngestionStatus.ready.value:
        await db.workspaces.update_one(
            {"_id": doc["workspace_id"]},
            {"$inc": {"ready_chunk_count": -int(doc.get("chunk_count", 0))},
             "$set": {"updated_at": now}},
        )
    await db.assets.update_one(
        {"_id": asset_oid},
        {"$set": {"ingestion_status": IngestionStatus.processing.value,
                  "chunk_count": 0, "error": None, "ingested_at": None, "updated_at": now}},
    )
    return await db.assets.find_one({"_id": asset_oid})


async def delete_asset_record(db: AsyncIOMotorDatabase, doc: dict) -> None:
    """Remove the Mongo doc and decrement workspace counters. Vectors + raw
    storage are dropped by the caller (route)."""
    now = utcnow()
    await db.assets.delete_one({"_id": doc["_id"]})
    dec = {"asset_count": -1}
    if doc.get("ingestion_status") == IngestionStatus.ready.value:
        dec["ready_chunk_count"] = -int(doc.get("chunk_count", 0))
    await db.workspaces.update_one(
        {"_id": doc["workspace_id"]}, {"$inc": dec, "$set": {"updated_at": now}}
    )
