"""Generation persistence + history. A generation is saved server-side at
stream end (ARCHITECTURE §6); the retrieval snapshot is stored on the document
so the debug panel survives later asset deletes/re-ingests (DATA_MODEL.md)."""
from __future__ import annotations

from typing import Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

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
) -> dict:
    now = utcnow()
    doc = {
        "_id": ObjectId(),
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
    db: AsyncIOMotorDatabase, workspace_oid: ObjectId, type_filter: str = "all"
) -> list[GenerationResponse]:
    query: dict = {"workspace_id": workspace_oid}
    if type_filter in ("text", "card"):
        query["type"] = type_filter
    cursor = db.generations.find(query).sort("created_at", -1)
    return [_to_response(doc) async for doc in cursor]


async def update_generation_output(
    db: AsyncIOMotorDatabase,
    workspace_oid: ObjectId,
    generation_id: str,
    output_patch: dict,
) -> Optional[dict]:
    """Merge a partial patch into a generation's `output` (Phase 1b attaches the
    selected card image; Phase 1.5 extends to inline field/template edits). Only
    provided keys are written, so a partial patch never wipes the rest of the
    output. Workspace-scoped, so a non-owner can't touch another's generation."""
    try:
        oid = ObjectId(generation_id)
    except Exception:
        return None
    doc = await db.generations.find_one({"_id": oid, "workspace_id": workspace_oid})
    if not doc:
        return None
    output = dict(doc.get("output") or {})
    output.update(output_patch)
    now = utcnow()
    await db.generations.update_one(
        {"_id": oid, "workspace_id": workspace_oid},
        {"$set": {"output": output, "updated_at": now}},
    )
    doc["output"] = output
    doc["updated_at"] = now
    return doc


async def get_generation(
    db: AsyncIOMotorDatabase, workspace_oid: ObjectId, generation_id: str
) -> Optional[dict]:
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
