"""Workspace CRUD. Slugs are unique per owner; the vector namespace is the
workspace id, so each workspace is isolated in its own Chroma collection."""
from __future__ import annotations

import re

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import settings
from app.models.common import (
    BrandExemplar,
    BrandImage,
    BrandLogo,
    CardPreset,
    UploadedFont,
    serialize_doc,
    utcnow,
)
from app.models.workspace import WorkspaceCreate, WorkspaceResponse, WorkspaceUpdate

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")

# Hard caps on the four capped `brand_profile` sub-collections. Enforced by the
# atomic guards below (not just the route pre-checks), so the invariant holds for
# any caller — see ARCH-05.
MAX_EXEMPLARS = 5
MAX_BRAND_IMAGES = 24
MAX_UPLOADED_FONTS = 8
MAX_CARD_PRESETS = 8


class WorkspaceWriteConflict(Exception):
    """A capped/deduped ``$push`` was rejected by its atomic guard — the cap is
    full or a uniqueness clash (``family``/``name``) lost a concurrent race. The
    data invariant is upheld regardless; the route maps this to a ``409``."""


def _room_for_one(field: str, cap: int) -> dict:
    """Filter clause matching only when array ``field`` has room for one more
    (current length < ``cap``). Makes the ``$push`` atomic — no read-then-write
    window — so two concurrent adds can't both exceed the cap (ARCH-05)."""
    return {"$expr": {"$lt": [{"$size": {"$ifNull": [f"${field}", []]}}, cap]}}


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
) -> WorkspaceResponse | None:
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    return _to_response(doc) if doc else None


async def _get_owned_doc(
    db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str
) -> dict | None:
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
) -> WorkspaceResponse | None:
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    if not doc:
        return None
    updates: dict = {"updated_at": utcnow()}
    if payload.name is not None and payload.name != doc["name"]:
        updates["name"] = payload.name
    if payload.brand_profile is not None:
        bp = payload.brand_profile.model_dump()
        # The brand PATCH edits colors/accent/fonts/voice and replaces the profile
        # whole; preserve the sub-collections that have their own endpoints (logo,
        # exemplars, brand images) so an identity Save can't silently wipe them.
        existing = doc.get("brand_profile") or {}
        for managed in ("logo", "exemplars", "brand_images", "uploaded_fonts", "card_presets"):
            if managed in existing:
                bp[managed] = existing[managed]
        updates["brand_profile"] = bp
    await db.workspaces.update_one({"_id": doc["_id"]}, {"$set": updates})
    doc.update(updates)
    return _to_response(doc)


async def set_workspace_logo(
    db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str, logo: BrandLogo
) -> WorkspaceResponse | None:
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
) -> tuple[WorkspaceResponse, str | None] | None:
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
) -> WorkspaceResponse | None:
    """Append an exemplar to `brand_profile.exemplars` (atomic capped $push).

    Raises `WorkspaceWriteConflict` if the cap is already reached (ARCH-05)."""
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    if not doc:
        return None
    now = utcnow()
    result = await db.workspaces.update_one(
        {"_id": doc["_id"], **_room_for_one("brand_profile.exemplars", MAX_EXEMPLARS)},
        {"$push": {"brand_profile.exemplars": exemplar.model_dump()}, "$set": {"updated_at": now}},
    )
    if result.matched_count == 0:
        raise WorkspaceWriteConflict
    bp = doc.setdefault("brand_profile", {})
    bp.setdefault("exemplars", []).append(exemplar.model_dump())
    doc["updated_at"] = now
    return _to_response(doc)


async def remove_workspace_exemplar(
    db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str, exemplar_id: str
) -> tuple[WorkspaceResponse, str | None] | None:
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


async def add_workspace_image(
    db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str, image: BrandImage
) -> WorkspaceResponse | None:
    """Append a brand image to `brand_profile.brand_images` (atomic capped $push).

    Raises `WorkspaceWriteConflict` if the cap is already reached (ARCH-05)."""
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    if not doc:
        return None
    now = utcnow()
    result = await db.workspaces.update_one(
        {"_id": doc["_id"], **_room_for_one("brand_profile.brand_images", MAX_BRAND_IMAGES)},
        {"$push": {"brand_profile.brand_images": image.model_dump()}, "$set": {"updated_at": now}},
    )
    if result.matched_count == 0:
        raise WorkspaceWriteConflict
    bp = doc.setdefault("brand_profile", {})
    bp.setdefault("brand_images", []).append(image.model_dump())
    doc["updated_at"] = now
    return _to_response(doc)


async def remove_workspace_image(
    db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str, image_id: str
) -> tuple[WorkspaceResponse, str | None] | None:
    """Pull a brand image by id; return the updated workspace + its storage key
    (so the caller can delete the bytes), or None if not owned."""
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    if not doc:
        return None
    images = (doc.get("brand_profile") or {}).get("brand_images") or []
    old_key = next((i.get("storage_key") for i in images if i.get("id") == image_id), None)
    now = utcnow()
    await db.workspaces.update_one(
        {"_id": doc["_id"]},
        {"$pull": {"brand_profile.brand_images": {"id": image_id}}, "$set": {"updated_at": now}},
    )
    bp = doc.setdefault("brand_profile", {})
    bp["brand_images"] = [i for i in images if i.get("id") != image_id]
    doc["updated_at"] = now
    return _to_response(doc), old_key


async def rename_workspace_image(
    db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str, image_id: str, name: str
) -> WorkspaceResponse | None:
    """Set a brand image's display name (targeted arrayFilters update). A blank
    name is ignored (keeps the existing label); long names clamp to 80."""
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    if not doc:
        return None
    clean = name.strip()[:80]
    now = utcnow()
    if clean:
        await db.workspaces.update_one(
            {"_id": doc["_id"]},
            {"$set": {"brand_profile.brand_images.$[img].name": clean, "updated_at": now}},
            array_filters=[{"img.id": image_id}],
        )
        for img in (doc.get("brand_profile") or {}).get("brand_images") or []:
            if img.get("id") == image_id:
                img["name"] = clean
    doc["updated_at"] = now
    return _to_response(doc)


def resolve_uploaded_font(brand_profile: dict, family: str | None) -> str | None:
    """Storage key of an uploaded font matching `family`, or None."""
    if not family:
        return None
    for f in (brand_profile or {}).get("uploaded_fonts") or []:
        if f.get("family") == family:
            return f.get("storage_key")
    return None


async def add_workspace_font(
    db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str, font: UploadedFont
) -> WorkspaceResponse | None:
    """Append an uploaded font to `brand_profile.uploaded_fonts` (atomic capped,
    `family`-deduped $push).

    Raises `WorkspaceWriteConflict` if the cap is reached or a font with the same
    `family` already exists (ARCH-05)."""
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    if not doc:
        return None
    now = utcnow()
    result = await db.workspaces.update_one(
        {
            "_id": doc["_id"],
            **_room_for_one("brand_profile.uploaded_fonts", MAX_UPLOADED_FONTS),
            "brand_profile.uploaded_fonts.family": {"$ne": font.family},
        },
        {"$push": {"brand_profile.uploaded_fonts": font.model_dump()},
         "$set": {"updated_at": now}},
    )
    if result.matched_count == 0:
        raise WorkspaceWriteConflict
    bp = doc.setdefault("brand_profile", {})
    bp.setdefault("uploaded_fonts", []).append(font.model_dump())
    doc["updated_at"] = now
    return _to_response(doc)


async def remove_workspace_font(
    db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str, font_id: str
) -> tuple[WorkspaceResponse, str | None] | None:
    """Pull an uploaded font by id; return the updated workspace + its storage key."""
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    if not doc:
        return None
    fonts = (doc.get("brand_profile") or {}).get("uploaded_fonts") or []
    old_key = next((f.get("storage_key") for f in fonts if f.get("id") == font_id), None)
    now = utcnow()
    await db.workspaces.update_one(
        {"_id": doc["_id"]},
        {"$pull": {"brand_profile.uploaded_fonts": {"id": font_id}}, "$set": {"updated_at": now}},
    )
    bp = doc.setdefault("brand_profile", {})
    bp["uploaded_fonts"] = [f for f in fonts if f.get("id") != font_id]
    doc["updated_at"] = now
    return _to_response(doc), old_key


async def add_workspace_card_preset(
    db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str, preset: CardPreset
) -> WorkspaceResponse | None:
    """Append a card preset to `brand_profile.card_presets` (atomic capped,
    `name`-deduped $push).

    Raises `WorkspaceWriteConflict` if the cap is reached or a preset with the
    same `name` already exists (ARCH-05)."""
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    if not doc:
        return None
    now = utcnow()
    result = await db.workspaces.update_one(
        {
            "_id": doc["_id"],
            **_room_for_one("brand_profile.card_presets", MAX_CARD_PRESETS),
            "brand_profile.card_presets.name": {"$ne": preset.name},
        },
        {"$push": {"brand_profile.card_presets": preset.model_dump(mode="json")},
         "$set": {"updated_at": now}},
    )
    if result.matched_count == 0:
        raise WorkspaceWriteConflict
    bp = doc.setdefault("brand_profile", {})
    bp.setdefault("card_presets", []).append(preset.model_dump(mode="json"))
    doc["updated_at"] = now
    return _to_response(doc)


async def remove_workspace_card_preset(
    db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str, preset_id: str
) -> WorkspaceResponse | None:
    """Pull a card preset by id (pure JSON — no stored bytes to delete)."""
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    if not doc:
        return None
    presets = (doc.get("brand_profile") or {}).get("card_presets") or []
    now = utcnow()
    await db.workspaces.update_one(
        {"_id": doc["_id"]},
        {"$pull": {"brand_profile.card_presets": {"id": preset_id}}, "$set": {"updated_at": now}},
    )
    bp = doc.setdefault("brand_profile", {})
    bp["card_presets"] = [p for p in presets if p.get("id") != preset_id]
    doc["updated_at"] = now
    return _to_response(doc)


async def delete_workspace(db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str) -> bool:
    """Delete a workspace and its assets + generations. Vectors are dropped by
    the caller (route) via the vector store so this service stays Mongo-only."""
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    if not doc:
        return False
    oid = doc["_id"]
    await db.assets.delete_many({"workspace_id": oid})
    await db.generations.delete_many({"workspace_id": oid})
    await db.templates.delete_many({"workspace_id": oid})
    await db.workspaces.delete_one({"_id": oid})
    return True
