"""Generation persistence + history. A generation is saved server-side at
stream end (ARCHITECTURE §6); the retrieval snapshot is stored on the document
so the debug panel survives later asset deletes/re-ingests (DATA_MODEL.md)."""
from __future__ import annotations

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.config import settings
from app.models.common import serialize_doc, utcnow
from app.models.generation import GenerationResponse


def _to_response(doc: dict) -> GenerationResponse:
    return GenerationResponse(**serialize_doc(doc))


async def create_generation(
    db: AsyncIOMotorDatabase,
    *,
    workspace_oid: ObjectId,
    owner_oid: ObjectId,
    type: str,
    brief: str,
    status: str,
    output: dict,
    retrieved_chunk_ids: list[str],
    retrieval_meta: list[dict],
    gen_id: ObjectId | None = None,
) -> dict:
    """`gen_id` lets the caller pre-generate the id (documents derive their file
    storage keys from it, so the files are built before the row is persisted)."""
    now = utcnow()
    doc = {
        "_id": gen_id or ObjectId(),
        "workspace_id": workspace_oid,
        "owner_id": owner_oid,
        "type": type,
        "brief": brief,
        "status": status,
        "output": output,
        "retrieved_chunk_ids": retrieved_chunk_ids,
        "retrieval_meta": retrieval_meta,
        "model": settings.ai_model,
        "embedding_query_model": settings.embedding_model,
        "created_at": now,
        "updated_at": now,
    }
    await db.generations.insert_one(doc)
    return doc


async def list_generations(
    db: AsyncIOMotorDatabase,
    workspace_oid: ObjectId,
    type_filter: str = "all",
    *,
    limit: int = 24,
    offset: int = 0,
) -> tuple[list[GenerationResponse], int | None]:
    query: dict = {"workspace_id": workspace_oid}
    if type_filter in ("text", "card", "document", "post_pack"):
        query["type"] = type_filter
    # Fetch one extra to detect a further page without a count() on the hot path.
    cursor = db.generations.find(query).sort("created_at", -1).skip(offset).limit(limit + 1)
    docs = [doc async for doc in cursor]
    has_more = len(docs) > limit
    items = [_to_response(d) for d in docs[:limit]]
    return items, (offset + limit if has_more else None)


async def count_generations(db: AsyncIOMotorDatabase, workspace_oid: ObjectId) -> int:
    return await db.generations.count_documents({"workspace_id": workspace_oid})


async def update_generation_output(
    db: AsyncIOMotorDatabase,
    workspace_oid: ObjectId,
    generation_id: str,
    output_patch: dict,
    nested_key: str | None = None,
) -> dict | None:
    """Merge a partial patch into a generation's `output` (Phase 1b attaches the
    selected card image; Phase 1.5 extends to inline field/template edits). Only
    provided keys are written, so a partial patch never wipes the rest of the
    output. Workspace-scoped, so a non-owner can't touch another's generation.

    `nested_key` merges the patch into a sub-object instead of the top level:
    a post_pack nests its card under `output.card` (Phase 3).

    Each key is `$set` on its own path, so two concurrent patches (say, removing
    the image while a text edit saves) both land instead of one overwriting the
    other with the `output` it read earlier."""
    try:
        oid = ObjectId(generation_id)
    except Exception:
        return None
    query: dict = {"_id": oid, "workspace_id": workspace_oid}
    base = f"output.{nested_key}" if nested_key else "output"
    # Dotted paths only work on an existing object (they can't extend a null).
    dotted = {f"{base}.{k}": v for k, v in output_patch.items()}
    doc = await _set_and_return(db, {**query, base: {"$type": "object"}}, dotted)
    if doc is not None:
        return doc
    return await _set_and_return(db, query, {base: output_patch})  # missing: create it


async def _set_and_return(db: AsyncIOMotorDatabase, query: dict, update: dict) -> dict | None:
    return await db.generations.find_one_and_update(
        query,
        {"$set": {**update, "updated_at": utcnow()}},
        return_document=ReturnDocument.AFTER,
    )


async def get_generation(
    db: AsyncIOMotorDatabase, workspace_oid: ObjectId, generation_id: str
) -> dict | None:
    try:
        oid = ObjectId(generation_id)
    except Exception:
        return None
    return await db.generations.find_one({"_id": oid, "workspace_id": workspace_oid})


async def delete_generation(
    db: AsyncIOMotorDatabase, workspace_oid: ObjectId, generation_id: str
) -> bool:
    try:
        oid = ObjectId(generation_id)
    except Exception:
        return False
    res = await db.generations.delete_one({"_id": oid, "workspace_id": workspace_oid})
    return res.deleted_count > 0


def to_response(doc: dict) -> GenerationResponse:
    return _to_response(doc)
