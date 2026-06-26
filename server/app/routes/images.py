"""Image routes.

Two surfaces (ARCHITECTURE §6):
  - global (`/api/images/...`)            — Unsplash search proxy + download tracking
  - workspace (`/api/workspaces/{id}/images/...`) — user upload + serving uploaded bytes

The Unsplash access key never leaves the server. Uploads are untrusted: the
content type is allow-listed, size-capped, and the storage key is derived
server-side (never from the raw filename) — the same defenses as asset upload.
"""
from __future__ import annotations

import os

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.models.image import (
    ImageUploadResponse,
    TrackDownloadRequest,
    UnsplashSearchResponse,
)
from app.services import unsplash_service
from app.services.storage_service import build_image_key, get_storage, safe_filename
from app.utils.dependencies import get_current_user, get_workspace_or_404

# Global (auth-only) router — mounted at /api/images
router = APIRouter()
# Workspace-scoped router — mounted at /api/workspaces/{workspace_id}/images
ws_router = APIRouter()

MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB
_IMAGE_CONTENT_TYPE = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
_ALLOWED = set(_IMAGE_CONTENT_TYPE.values())


@router.get("/unsplash/search", response_model=UnsplashSearchResponse)
async def unsplash_search(
    q: str,
    page: int = 1,
    _: object = Depends(get_current_user),
):
    query = q.strip()
    if not query:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty query.")
    try:
        return await unsplash_service.search(query, page)
    except unsplash_service.UnsplashError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router.post("/unsplash/track", status_code=status.HTTP_204_NO_CONTENT)
async def unsplash_track(
    payload: TrackDownloadRequest,
    _: object = Depends(get_current_user),
):
    """Fire Unsplash's download-tracking endpoint on selection (license
    requirement). Best-effort — a tracking failure must not block selection."""
    try:
        await unsplash_service.track_download(payload.download_location)
    except Exception:  # noqa: BLE001 — best-effort, never surface to the user
        pass


def resolve_image_content_type(filename: str, provided: str | None) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in _IMAGE_CONTENT_TYPE:
        return _IMAGE_CONTENT_TYPE[ext]
    if provided in _ALLOWED:
        return provided  # type: ignore[return-value]
    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Unsupported image type. Upload a JPG, PNG, or WebP.",
    )


@ws_router.post("/upload", response_model=ImageUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile,
    workspace: dict = Depends(get_workspace_or_404),
):
    filename = file.filename or "image"
    content_type = resolve_image_content_type(filename, file.content_type)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file.")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds the {MAX_IMAGE_BYTES // (1024 * 1024)} MB limit.",
        )

    workspace_id = str(workspace["_id"])
    image_id = str(ObjectId())
    clean_name = safe_filename(filename)
    storage_key = build_image_key(workspace_id, image_id, clean_name)
    await get_storage().save(storage_key, data)
    _ = content_type  # validated above; served content type is re-derived on GET
    return ImageUploadResponse(
        storage_key=storage_key,
        url=f"/api/workspaces/{workspace_id}/images/file/{image_id}/{clean_name}",
    )


@ws_router.get("/file/{image_id}/{filename}")
async def serve_image(
    image_id: str,
    filename: str,
    workspace: dict = Depends(get_workspace_or_404),
):
    """Serve an uploaded card image. Ownership is enforced by
    `get_workspace_or_404`; the storage key is rebuilt server-side (the
    path-traversal guard in storage rejects anything that escapes the root)."""
    workspace_id = str(workspace["_id"])
    key = build_image_key(workspace_id, image_id, filename)
    try:
        data = await get_storage().read(key)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    content_type = _IMAGE_CONTENT_TYPE.get(
        os.path.splitext(filename)[1].lower(), "application/octet-stream"
    )
    return Response(content=data, media_type=content_type)
