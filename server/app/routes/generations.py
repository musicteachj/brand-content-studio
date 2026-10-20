"""Content history routes: list (with type filter), get one, delete."""
from __future__ import annotations

import logging

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_database
from app.models.generation import (
    GenerationCount,
    GenerationPage,
    GenerationResponse,
    GenerationUpdate,
)
from app.services import generations_service
from app.services.storage_service import build_document_prefix, get_storage
from app.utils.dependencies import get_workspace_or_404, require_not_demo

router = APIRouter()
logger = logging.getLogger(__name__)

# PATCH fields an explicit null clears; a null for any other field is ignored.
CLEARABLE_FIELDS = {"image"}


@router.get("", response_model=GenerationPage)
async def list_generations(
    type: str = Query("all", pattern="^(all|text|card|document|post_pack)$"),
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
    workspace: dict = Depends(get_workspace_or_404),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    items, next_offset = await generations_service.list_generations(
        db, workspace["_id"], type, limit=limit, offset=offset
    )
    return GenerationPage(items=items, next_offset=next_offset)


@router.get("/count", response_model=GenerationCount)
async def count_generations(
    workspace: dict = Depends(get_workspace_or_404),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    return GenerationCount(count=await generations_service.count_generations(db, workspace["_id"]))


@router.get("/{generation_id}", response_model=GenerationResponse)
async def get_generation(
    generation_id: str,
    workspace: dict = Depends(get_workspace_or_404),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    doc = await generations_service.get_generation(db, workspace["_id"], generation_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found")
    return generations_service.to_response(doc)


@router.patch("/{generation_id}", response_model=GenerationResponse)
async def update_generation(
    generation_id: str,
    payload: GenerationUpdate,
    workspace: dict = Depends(get_workspace_or_404),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Attach the selected card image (and, from Phase 1.5, inline field/template
    edits) to a generation's `output`. Allowed for the demo user: these are the
    user's own generations, not the protected seed corpus."""
    patch = payload.model_dump(exclude_none=True)
    # An explicit null clears only the image ("Remove image", QA-07); a null for
    # any other field is ignored, so it can't wipe the template, copy, or accent.
    for key in CLEARABLE_FIELDS & payload.model_fields_set:
        if getattr(payload, key) is None:
            patch[key] = None
    if not patch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update."
        )
    existing = await generations_service.get_generation(db, workspace["_id"], generation_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found")
    # These fields are card-shaped (image/template/fields/accent). A `card` carries
    # them at the top of `output`; a `post_pack` nests its card under `output.card`.
    # Refuse anything else (text/document); merging would corrupt its shape.
    gen_type = existing.get("type")
    if gen_type == "card":
        nested_key = None
    elif gen_type == "post_pack":
        nested_key = "card"
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only card and post-pack generations can be edited.",
        )
    # The per-card accent must be one of the workspace's own brand-palette colors,
    # never an arbitrary hex (keeps cards on-brand; DESIGN §7).
    accent = patch.get("accent_hex")
    if accent is not None:
        palette = {
            c["hex"].lower()
            for c in (workspace.get("brand_profile") or {}).get("colors") or []
            if isinstance(c, dict) and isinstance(c.get("hex"), str)
        }
        if accent.lower() not in palette:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="accent_hex must be one of the workspace's brand colors.",
            )
    doc = await generations_service.update_generation_output(
        db, workspace["_id"], generation_id, patch, nested_key=nested_key
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found")
    return generations_service.to_response(doc)


@router.delete("/{generation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_generation(
    generation_id: str,
    workspace: dict = Depends(get_workspace_or_404),
    _: object = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    ok = await generations_service.delete_generation(db, workspace["_id"], generation_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found")
    # Its built .docx/.pdf/.pptx go too (they used to stay in storage). Only after
    # the delete succeeded, so the id is a real generation in this workspace, and
    # normalized the way the files were saved (ObjectId accepts uppercase hex).
    # Card images are left alone: an uploaded one may be shared with the brand
    # image library. A cleanup failure is logged, not raised: the generation is
    # already gone, so the delete did succeed.
    prefix = build_document_prefix(str(workspace["_id"]), str(ObjectId(generation_id)))
    try:
        await get_storage().delete_prefix(prefix)
    except Exception:  # noqa: BLE001
        logger.exception("Couldn't remove the files for deleted generation %s", generation_id)
