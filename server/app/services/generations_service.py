"""Generation persistence + history. A generation is saved server-side at
stream end (ARCHITECTURE §6); the retrieval snapshot is stored on the document
so the debug panel survives later asset deletes/re-ingests (DATA_MODEL.md).

Every read and write is scoped (`scope_filter`): the owner reaches the whole workspace,
a demo visitor reaches only their own session's work plus the ready-made examples, and
no one edits or deletes an example. `session_id` is keyword-only and required on every
scoped call, so a caller can't forget it and fall back to the owner's scope."""
from __future__ import annotations

from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.config import settings
from app.models.common import serialize_doc, utcnow
from app.models.generation import GenerationResponse


def _to_response(doc: dict) -> GenerationResponse:
    return GenerationResponse(**serialize_doc(doc))


def scope_filter(workspace_oid: ObjectId, session_id: str | None) -> dict:
    """The generations a user may read: the whole workspace for the owner (`session_id`
    None); for a visitor, their own session's work and the examples."""
    if session_id is None:
        return {"workspace_id": workspace_oid}
    return {
        "workspace_id": workspace_oid,
        "$or": [{"session_id": session_id}, {"is_example": True}],
    }


def _write_filter(workspace_oid: ObjectId, session_id: str | None) -> dict:
    """The generations a user may change or delete: never an example, and for a visitor
    only their own session's work."""
    query: dict = {"workspace_id": workspace_oid, "is_example": {"$ne": True}}
    if session_id is not None:
        query["session_id"] = session_id
    return query


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
    session_id: str | None = None,
    expires_at: datetime | None = None,
) -> dict:
    """`gen_id` lets the caller pre-generate the id (documents derive their file
    storage keys from it, so the files are built before the row is persisted).

    A visitor's generation carries its session ID and the session's expiry: the ID scopes
    it to that visitor, and the hourly cleanup removes it (files first) once it expires."""
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
    if session_id is not None:
        doc["session_id"] = session_id
        doc["expires_at"] = expires_at
    await db.generations.insert_one(doc)
    return doc


async def list_generations(
    db: AsyncIOMotorDatabase,
    workspace_oid: ObjectId,
    type_filter: str = "all",
    *,
    session_id: str | None,
    limit: int = 24,
    offset: int = 0,
) -> tuple[list[GenerationResponse], int | None]:
    query = scope_filter(workspace_oid, session_id)
    if type_filter in ("text", "card", "document", "post_pack"):
        query["type"] = type_filter
    # Fetch one extra to detect a further page without a count() on the hot path.
    cursor = db.generations.find(query).sort("created_at", -1).skip(offset).limit(limit + 1)
    docs = [doc async for doc in cursor]
    has_more = len(docs) > limit
    items = [_to_response(d) for d in docs[:limit]]
    return items, (offset + limit if has_more else None)


async def count_generations(
    db: AsyncIOMotorDatabase, workspace_oid: ObjectId, *, session_id: str | None
) -> int:
    return await db.generations.count_documents(scope_filter(workspace_oid, session_id))


async def update_generation_output(
    db: AsyncIOMotorDatabase,
    workspace_oid: ObjectId,
    generation_id: str,
    output_patch: dict,
    nested_key: str | None = None,
    *,
    session_id: str | None,
) -> dict | None:
    """Merge a partial patch into a generation's `output` (Phase 1b attaches the
    selected card image; Phase 1.5 extends to inline field/template edits). Only
    provided keys are written, so a partial patch never wipes the rest of the
    output. Workspace-scoped, so a non-owner can't touch another's generation; a visitor
    reaches only their own session's work, and an example is never changed.

    `nested_key` merges the patch into a sub-object instead of the top level:
    a post_pack nests its card under `output.card` (Phase 3).

    Each key is `$set` on its own path, so two concurrent patches (say, removing
    the image while a text edit saves) both land instead of one overwriting the
    other with the `output` it read earlier."""
    try:
        oid = ObjectId(generation_id)
    except Exception:
        return None
    query: dict = {"_id": oid, **_write_filter(workspace_oid, session_id)}
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


async def image_key_in_use(
    db: AsyncIOMotorDatabase, workspace_oid: ObjectId, storage_key: str
) -> bool:
    """Whether any generation in the workspace still shows this stored image: a
    card's `output.image` or a post_pack's nested `output.card.image`. A card
    picked from the brand-image library keeps the library image's own key."""
    doc = await db.generations.find_one(
        {
            "workspace_id": workspace_oid,
            "type": {"$in": ["card", "post_pack"]},  # uses the (workspace_id, type) index
            "$or": [
                {"output.image.storage_key": storage_key},
                {"output.card.image.storage_key": storage_key},
            ],
        },
        projection={"_id": 1},
    )
    return doc is not None


async def get_generation(
    db: AsyncIOMotorDatabase,
    workspace_oid: ObjectId,
    generation_id: str,
    *,
    session_id: str | None,
) -> dict | None:
    try:
        oid = ObjectId(generation_id)
    except Exception:
        return None
    return await db.generations.find_one({"_id": oid, **scope_filter(workspace_oid, session_id)})


async def delete_generation(
    db: AsyncIOMotorDatabase,
    workspace_oid: ObjectId,
    generation_id: str,
    *,
    session_id: str | None,
) -> bool:
    try:
        oid = ObjectId(generation_id)
    except Exception:
        return False
    res = await db.generations.delete_one({"_id": oid, **_write_filter(workspace_oid, session_id)})
    return res.deleted_count > 0


def to_response(doc: dict) -> GenerationResponse:
    return _to_response(doc)
