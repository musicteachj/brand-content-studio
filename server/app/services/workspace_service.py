"""Workspace CRUD. Slugs are unique per owner; the vector namespace is the
workspace id, so each workspace is isolated in its own Chroma collection."""
from __future__ import annotations

import re
from typing import Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import settings
from app.models.common import BrandExemplar, BrandLogo, serialize_doc, utcnow
from app.models.workspace import WorkspaceCreate, WorkspaceResponse, WorkspaceUpdate

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")

MAX_EXEMPLARS = 5


def _slugify(name: str) -> str:
    slug = _SLUG_STRIP.sub("-", name.lower()).strip("-")
    return slug or "workspace"


async def _unique_slug(db: AsyncIOMotorDatabase, owner_id: ObjectId, name: str) -> str:
    base = _slugify(name)
    slug = base
    n = 2
    while await db.workspaces.find_one({"owner_id": owner_id, "slug": slug}):
        slug = f"{base}-{n}"
        n += 1
    return slug


def _to_response(doc: dict) -> WorkspaceResponse:
    return WorkspaceResponse(**serialize_doc(doc))


async def list_workspaces(db: AsyncIOMotorDatabase, owner_id: str) -> list[WorkspaceResponse]:
    cursor = db.workspaces.find({"owner_id": ObjectId(owner_id)}).sort("created_at", -1)
    return [_to_response(doc) async for doc in cursor]


async def get_workspace(
    db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str
) -> Optional[WorkspaceResponse]:
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    return _to_response(doc) if doc else None


async def _get_owned_doc(
    db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str
) -> Optional[dict]:
    try:
        oid = ObjectId(workspace_id)
    except Exception:
        return None
    return await db.workspaces.find_one({"_id": oid, "owner_id": ObjectId(owner_id)})


async def create_workspace(
    db: AsyncIOMotorDatabase, owner_id: str, payload: WorkspaceCreate
) -> WorkspaceResponse:
    owner_oid = ObjectId(owner_id)
    workspace_oid = ObjectId()
    now = utcnow()
    slug = await _unique_slug(db, owner_oid, payload.name)
    doc = {
        "_id": workspace_oid,
        "owner_id": owner_oid,
        "name": payload.name,
        "slug": slug,
        "brand_profile": payload.brand_profile.model_dump(),
        "vector_namespace": str(workspace_oid),
        "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim,
        "asset_count": 0,
        "ready_chunk_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    await db.workspaces.insert_one(doc)
    return _to_response(doc)


async def update_workspace(
    db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str, payload: WorkspaceUpdate
) -> Optional[WorkspaceResponse]:
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    if not doc:
        return None
    updates: dict = {"updated_at": utcnow()}
    if payload.name is not None and payload.name != doc["name"]:
        updates["name"] = payload.name
    if payload.brand_profile is not None:
        updates["brand_profile"] = payload.brand_profile.model_dump()
    await db.workspaces.update_one({"_id": doc["_id"]}, {"$set": updates})
    doc.update(updates)
    return _to_response(doc)


async def set_workspace_logo(
    db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str, logo: BrandLogo
) -> Optional[WorkspaceResponse]:
    """Set just `brand_profile.logo` (a targeted update, so it never clobbers the
    rest of the profile). Returns the updated workspace, or None if not owned."""
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    if not doc:
        return None
    now = utcnow()
    await db.workspaces.update_one(
        {"_id": doc["_id"]},
        {"$set": {"brand_profile.logo": logo.model_dump(), "updated_at": now}},
    )
    doc.setdefault("brand_profile", {})["logo"] = logo.model_dump()
    doc["updated_at"] = now
    return _to_response(doc)


async def clear_workspace_logo(
    db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str
) -> Optional[tuple[WorkspaceResponse, Optional[str]]]:
    """Unset `brand_profile.logo`. Returns the updated workspace plus the old
    storage key (so the caller can delete the stored bytes), or None if not owned."""
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    if not doc:
        return None
    old = (doc.get("brand_profile") or {}).get("logo") or {}
    old_key = old.get("storage_key")
    now = utcnow()
    await db.workspaces.update_one(
        {"_id": doc["_id"]},
        {"$set": {"brand_profile.logo": None, "updated_at": now}},
    )
    doc.setdefault("brand_profile", {})["logo"] = None
    doc["updated_at"] = now
    return _to_response(doc), old_key


async def add_workspace_exemplar(
    db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str, exemplar: BrandExemplar
) -> Optional[WorkspaceResponse]:
    """Append an exemplar to `brand_profile.exemplars` (targeted $push)."""
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    if not doc:
        return None
    now = utcnow()
    await db.workspaces.update_one(
        {"_id": doc["_id"]},
        {"$push": {"brand_profile.exemplars": exemplar.model_dump()}, "$set": {"updated_at": now}},
    )
    bp = doc.setdefault("brand_profile", {})
    bp.setdefault("exemplars", []).append(exemplar.model_dump())
    doc["updated_at"] = now
    return _to_response(doc)


async def remove_workspace_exemplar(
    db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str, exemplar_id: str
) -> Optional[tuple[WorkspaceResponse, Optional[str]]]:
    """Pull an exemplar by id; return the updated workspace + its storage key (so
    the caller can delete the bytes), or None if not owned."""
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    if not doc:
        return None
    exemplars = (doc.get("brand_profile") or {}).get("exemplars") or []
    old_key = next((e.get("storage_key") for e in exemplars if e.get("id") == exemplar_id), None)
    now = utcnow()
    await db.workspaces.update_one(
        {"_id": doc["_id"]},
        {"$pull": {"brand_profile.exemplars": {"id": exemplar_id}}, "$set": {"updated_at": now}},
    )
    bp = doc.setdefault("brand_profile", {})
    bp["exemplars"] = [e for e in exemplars if e.get("id") != exemplar_id]
    doc["updated_at"] = now
    return _to_response(doc), old_key


async def delete_workspace(db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str) -> bool:
    """Delete a workspace and its assets + generations. Vectors are dropped by
    the caller (route) via the vector store so this service stays Mongo-only."""
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    if not doc:
        return False
    oid = doc["_id"]
    await db.assets.delete_many({"workspace_id": oid})
    await db.generations.delete_many({"workspace_id": oid})
    await db.workspaces.delete_one({"_id": oid})
    return True
