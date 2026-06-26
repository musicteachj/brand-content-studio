"""Workspace CRUD routes. All workspace-scoped sub-routers (assets, generate,
generations) hang off `/workspaces/{workspace_id}` and go through
`get_workspace_or_404` for ownership."""
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_database
from app.models.common import BrandLogo
from app.models.user import UserInDB
from app.models.workspace import (
    BrandExtractResponse,
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from app.rag.vector_store import get_vector_store
from app.routes.images import MAX_IMAGE_BYTES, resolve_image_content_type
from app.services import workspace_service
from app.services.brand_extract_service import BrandExtractService
from app.services.storage_service import build_image_key, get_storage, safe_filename
from app.utils.dependencies import get_current_user, get_workspace_or_404, require_not_demo

router = APIRouter()


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
    filename = file.filename or "logo"
    resolve_image_content_type(filename, file.content_type)  # validates type (415)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file.")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds the {MAX_IMAGE_BYTES // (1024 * 1024)} MB limit.",
        )

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
async def extract_brand(
    file: UploadFile,
    workspace: dict = Depends(get_workspace_or_404),
    service: BrandExtractService = Depends(BrandExtractService),
):
    """Propose a brand profile (palette + voice + fonts) from an uploaded image.

    Returns a **proposal only** — nothing is persisted; the client reviews it and
    applies it through the brand PATCH. Allowed for the demo user (it's generative,
    not a mutation — DECISIONS #15); validated like the image/logo uploads."""
    filename = file.filename or "image"
    media_type = resolve_image_content_type(filename, file.content_type)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file.")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds the {MAX_IMAGE_BYTES // (1024 * 1024)} MB limit.",
        )
    _ = workspace  # ownership enforced by the dependency
    return await service.propose(data, media_type)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    namespace = workspace["vector_namespace"]
    await workspace_service.delete_workspace(db, str(workspace["_id"]), current_user.id)
    await get_vector_store().delete_workspace(namespace)
