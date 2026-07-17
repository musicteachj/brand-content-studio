"""Workspace CRUD routes. All workspace-scoped sub-routers (assets, generate,
generations) hang off `/workspaces/{workspace_id}` and go through
`get_workspace_or_404` for ownership."""
import re

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_database
from app.limits import (
    MAX_BRAND_IMAGES,
    MAX_CARD_PRESETS,
    MAX_EXEMPLARS,
    MAX_UPLOADED_FONTS,
)
from app.models.common import BrandExemplar, BrandImage, BrandLogo, CardPreset, UploadedFont
from app.models.user import UserInDB
from app.models.workspace import (
    BrandExtractResponse,
    BrandImageRename,
    CardPresetCreate,
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from app.rag.vector_store import get_vector_store
from app.services import workspace_service
from app.services.brand_extract_service import BrandExtractService
from app.services.storage_service import build_font_key, build_image_key, get_storage, safe_filename
from app.services.upload_service import FONT_POLICY, IMAGE_POLICY, read_upload
from app.services.workspace_service import WorkspaceWriteConflict
from app.utils.dependencies import (
    enforce_demo_generation_quota,
    get_current_user,
    get_workspace_or_404,
    require_not_demo,
)
from app.utils.ratelimit import GENERATE_RATE_LIMIT, limiter

router = APIRouter()

# A font family is a user-typed label that gets interpolated into CSS/@font-face
# on the client; restrict it to an allow-list so it can't carry CSS-injection
# characters (the client also uses the CSSOM FontFace API as the primary defense).
_FONT_FAMILY_RE = re.compile(r"^[A-Za-z0-9 ._-]{1,80}$")


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    return await workspace_service.list_workspaces(db, current_user.id)


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceCreate,
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    return await workspace_service.create_workspace(db, current_user.id, payload)


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace: dict = Depends(get_workspace_or_404),
):
    from app.models.common import serialize_doc

    return WorkspaceResponse(**serialize_doc(workspace))


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    payload: WorkspaceUpdate,
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    updated = await workspace_service.update_workspace(
        db, str(workspace["_id"]), current_user.id, payload
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return updated


@router.post("/{workspace_id}/logo", response_model=WorkspaceResponse)
async def upload_logo(
    file: UploadFile,
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Upload a brand logo. Mirrors the card-image upload defenses (allow-listed
    type, size cap, server-derived key) and stores the result on
    `brand_profile.logo`. Served by the existing image route."""
    data, filename, _ = await read_upload(file, IMAGE_POLICY, default_name="logo")
    workspace_id = str(workspace["_id"])
    logo_id = str(ObjectId())
    clean_name = safe_filename(filename)
    storage_key = build_image_key(workspace_id, logo_id, clean_name)
    await get_storage().save(storage_key, data)
    logo = BrandLogo(
        storage_key=storage_key,
        url=f"/api/workspaces/{workspace_id}/images/file/{logo_id}/{clean_name}",
    )
    updated = await workspace_service.set_workspace_logo(
        db, workspace_id, current_user.id, logo
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return updated


@router.delete("/{workspace_id}/logo", response_model=WorkspaceResponse)
async def delete_logo(
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Remove the brand logo and delete its stored bytes."""
    result = await workspace_service.clear_workspace_logo(
        db, str(workspace["_id"]), current_user.id
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    updated, old_key = result
    if old_key:
        await get_storage().delete(old_key)
    return updated


@router.post("/{workspace_id}/brand/extract", response_model=BrandExtractResponse)
@limiter.limit(GENERATE_RATE_LIMIT)
async def extract_brand(
    request: Request,
    file: UploadFile,
    workspace: dict = Depends(get_workspace_or_404),
    service: BrandExtractService = Depends(BrandExtractService),
    _quota: None = Depends(enforce_demo_generation_quota),
):
    """Propose a brand profile (palette + voice + fonts) from an uploaded image.

    Returns a **proposal only** — nothing is persisted; the client reviews it and
    applies it through the brand PATCH. Allowed for the demo user (it's generative,
    not a mutation — DECISIONS #15); validated like the image/logo uploads."""
    data, _, media_type = await read_upload(file, IMAGE_POLICY, default_name="image")
    _ = workspace  # ownership enforced by the dependency
    return await service.propose(data, media_type)


@router.post("/{workspace_id}/exemplars", response_model=WorkspaceResponse)
async def add_exemplar(
    file: UploadFile,
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
    service: BrandExtractService = Depends(BrandExtractService),
):
    """Upload a past brand card → extract a style note (vision) → store it on
    `brand_profile.exemplars`. Capped; extract runs before storage so a vision
    failure persists nothing. Demo-blocked (it mutates the workspace)."""
    existing = (workspace.get("brand_profile") or {}).get("exemplars") or []
    if len(existing) >= MAX_EXEMPLARS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"At most {MAX_EXEMPLARS} example cards per workspace.",
        )
    data, filename, media_type = await read_upload(file, IMAGE_POLICY, default_name="card")
    note = await service.propose_exemplar_note(data, media_type)
    workspace_id = str(workspace["_id"])
    exemplar_id = str(ObjectId())
    clean_name = safe_filename(filename)
    storage_key = build_image_key(workspace_id, exemplar_id, clean_name)
    await get_storage().save(storage_key, data)
    exemplar = BrandExemplar(
        id=exemplar_id,
        storage_key=storage_key,
        url=f"/api/workspaces/{workspace_id}/images/file/{exemplar_id}/{clean_name}",
        style_note=note,
    )
    try:
        updated = await workspace_service.add_workspace_exemplar(
            db, workspace_id, current_user.id, exemplar
        )
    except WorkspaceWriteConflict:
        # Lost the race against a concurrent add (the pre-check passed but the cap
        # filled between then and the write) — drop the bytes we just stored.
        await get_storage().delete(storage_key)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"At most {MAX_EXEMPLARS} example cards per workspace.",
        ) from None
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return updated


@router.delete("/{workspace_id}/exemplars/{exemplar_id}", response_model=WorkspaceResponse)
async def delete_exemplar(
    exemplar_id: str,
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Remove an exemplar and delete its stored bytes."""
    result = await workspace_service.remove_workspace_exemplar(
        db, str(workspace["_id"]), current_user.id, exemplar_id
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    updated, old_key = result
    if old_key:
        await get_storage().delete(old_key)
    return updated


@router.post("/{workspace_id}/brand-images", response_model=WorkspaceResponse)
async def add_brand_image(
    file: UploadFile,
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Save an image to the workspace's reusable brand-image library
    (`brand_profile.brand_images`). No model call — just validate + store, so it
    can later be picked as a card image. Capped; demo-blocked (it mutates)."""
    existing = (workspace.get("brand_profile") or {}).get("brand_images") or []
    if len(existing) >= MAX_BRAND_IMAGES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"At most {MAX_BRAND_IMAGES} brand images per workspace.",
        )
    data, filename, _ = await read_upload(file, IMAGE_POLICY, default_name="image")
    workspace_id = str(workspace["_id"])
    image_id = str(ObjectId())
    clean_name = safe_filename(filename)
    storage_key = build_image_key(workspace_id, image_id, clean_name)
    await get_storage().save(storage_key, data)
    image = BrandImage(
        id=image_id,
        storage_key=storage_key,
        url=f"/api/workspaces/{workspace_id}/images/file/{image_id}/{clean_name}",
        name=filename,
    )
    try:
        updated = await workspace_service.add_workspace_image(
            db, workspace_id, current_user.id, image
        )
    except WorkspaceWriteConflict:
        await get_storage().delete(storage_key)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"At most {MAX_BRAND_IMAGES} brand images per workspace.",
        ) from None
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return updated


@router.delete("/{workspace_id}/brand-images/{image_id}", response_model=WorkspaceResponse)
async def delete_brand_image(
    image_id: str,
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Remove a brand image from the library and delete its stored bytes. Images
    already baked onto past cards are unaffected (copied onto the generation)."""
    result = await workspace_service.remove_workspace_image(
        db, str(workspace["_id"]), current_user.id, image_id
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    updated, old_key = result
    if old_key:
        await get_storage().delete(old_key)
    return updated


@router.patch("/{workspace_id}/brand-images/{image_id}", response_model=WorkspaceResponse)
async def rename_brand_image(
    image_id: str,
    payload: BrandImageRename,
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Rename a brand image's display label. Demo-blocked (it mutates)."""
    updated = await workspace_service.rename_workspace_image(
        db, str(workspace["_id"]), current_user.id, image_id, payload.name
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return updated


@router.post("/{workspace_id}/fonts", response_model=WorkspaceResponse)
async def add_font(
    name: str = Form(...),
    file: UploadFile = File(...),
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Upload a `.ttf` brand font (name = the family handle). Demo-blocked, capped."""
    existing = (workspace.get("brand_profile") or {}).get("uploaded_fonts") or []
    if len(existing) >= MAX_UPLOADED_FONTS:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"At most {MAX_UPLOADED_FONTS} fonts per workspace.")
    family = name.strip()[:80]
    if not family:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A font name is required.")
    if not _FONT_FAMILY_RE.match(family):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Font name may use letters, numbers, spaces, and . _ - only.",
        )
    if any(f.get("family") == family for f in existing):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A font with that name exists.")
    data, filename, _ = await read_upload(file, FONT_POLICY, default_name="font.ttf")
    workspace_id = str(workspace["_id"])
    font_id = str(ObjectId())
    clean_name = safe_filename(filename)
    key = build_font_key(workspace_id, font_id, clean_name)
    await get_storage().save(key, data)
    font = UploadedFont(
        id=font_id, family=family, storage_key=key,
        url=f"/api/workspaces/{workspace_id}/fonts/file/{font_id}/{clean_name}",
    )
    try:
        updated = await workspace_service.add_workspace_font(db, workspace_id, current_user.id, font)
    except WorkspaceWriteConflict:
        await get_storage().delete(key)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Font limit reached or a font with that name already exists.",
        ) from None
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return updated


@router.delete("/{workspace_id}/fonts/{font_id}", response_model=WorkspaceResponse)
async def delete_font(
    font_id: str,
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Remove an uploaded font and delete its stored bytes. A card/PDF already
    rendered is unaffected; a role still naming it falls back to serif/Georgia."""
    result = await workspace_service.remove_workspace_font(
        db, str(workspace["_id"]), current_user.id, font_id
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    updated, old_key = result
    if old_key:
        await get_storage().delete(old_key)
    return updated


@router.get("/{workspace_id}/fonts/file/{font_id}/{filename}")
async def serve_font(
    font_id: str,
    filename: str,
    workspace: dict = Depends(get_workspace_or_404),
):
    """Serve an uploaded font's bytes. Ownership via the dependency; the key is
    rebuilt server-side (storage's traversal guard rejects anything escaping root)."""
    key = build_font_key(str(workspace["_id"]), font_id, filename)
    try:
        data = await get_storage().read(key)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Font not found") from None
    return Response(content=data, media_type="font/ttf")


@router.post("/{workspace_id}/card-presets", response_model=WorkspaceResponse)
async def add_card_preset(
    payload: CardPresetCreate,
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Save a named card preset (template + accent). Demo-blocked, capped, deduped
    by name. `accent_hex` shape is validated on the `CardPreset` model."""
    existing = (workspace.get("brand_profile") or {}).get("card_presets") or []
    if len(existing) >= MAX_CARD_PRESETS:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"At most {MAX_CARD_PRESETS} card presets per workspace.")
    name = payload.name.strip()[:80]
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A preset name is required.")
    if any(p.get("name") == name for p in existing):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A preset with that name exists.")
    preset = CardPreset(
        id=str(ObjectId()), name=name, template_id=payload.template_id, accent_hex=payload.accent_hex
    )
    try:
        updated = await workspace_service.add_workspace_card_preset(
            db, str(workspace["_id"]), current_user.id, preset
        )
    except WorkspaceWriteConflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Preset limit reached or a preset with that name already exists.",
        ) from None
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return updated


@router.delete("/{workspace_id}/card-presets/{preset_id}", response_model=WorkspaceResponse)
async def delete_card_preset(
    preset_id: str,
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Remove a card preset. Cards already generated with it are unaffected (the
    template + accent are copied onto the generation)."""
    updated = await workspace_service.remove_workspace_card_preset(
        db, str(workspace["_id"]), current_user.id, preset_id
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return updated


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    namespace = workspace["vector_namespace"]
    await workspace_service.delete_workspace(db, str(workspace["_id"]), current_user.id)
    await get_vector_store().delete_workspace(namespace)
