"""Asset routes — upload (202 + BackgroundTask ingestion), list, get, delete.

Uploads are untrusted: type + size are validated, the storage key is derived
server-side, and ingestion runs out-of-band so the request returns immediately
and the UI polls the status pill."""
from __future__ import annotations

import os

from bson import ObjectId
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_database
from app.models.asset import AssetKind, AssetResponse
from app.rag.vector_store import get_vector_store
from app.services import asset_service
from app.services.ingestion_service import ingest_asset
from app.services.storage_service import build_storage_key, get_storage
from app.utils.dependencies import get_workspace_or_404, require_not_demo

router = APIRouter()

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

# Map common extensions → canonical content types (browsers are inconsistent,
# e.g. .md often arrives as application/octet-stream).
_EXT_CONTENT_TYPE = {
    ".pdf": "application/pdf",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
}
_ALLOWED = set(_EXT_CONTENT_TYPE.values())


def _resolve_content_type(filename: str, provided: str | None) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in _EXT_CONTENT_TYPE:
        return _EXT_CONTENT_TYPE[ext]
    if provided in _ALLOWED:
        return provided  # type: ignore[return-value]
    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Unsupported file type. Upload a PDF, Markdown, or plain-text file.",
    )


@router.post("", response_model=AssetResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_asset(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    asset_kind: AssetKind = Form(...),
    workspace: dict = Depends(get_workspace_or_404),
    _: object = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    filename = file.filename or "upload"
    content_type = _resolve_content_type(filename, file.content_type)

    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
        )

    workspace_oid = workspace["_id"]
    # Store the raw file *before* writing any Mongo state, so a storage failure
    # doesn't orphan an asset doc or inflate the workspace counters.
    asset_oid = ObjectId()
    storage_key = build_storage_key(str(workspace_oid), str(asset_oid), filename)
    await get_storage().save(storage_key, data)

    doc = await asset_service.create_asset(
        db,
        workspace_oid,
        asset_oid=asset_oid,
        filename=filename,
        content_type=content_type,
        asset_kind=asset_kind,
        size_bytes=len(data),
        storage_key=storage_key,
    )

    background_tasks.add_task(ingest_asset, str(asset_oid), workspace["vector_namespace"])
    return await asset_service.asset_response(doc)


@router.get("", response_model=list[AssetResponse])
async def list_assets(
    workspace: dict = Depends(get_workspace_or_404),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    return await asset_service.list_assets(db, workspace["_id"])


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: str,
    workspace: dict = Depends(get_workspace_or_404),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    doc = await asset_service.get_asset(db, workspace["_id"], asset_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return await asset_service.asset_response(doc)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: str,
    workspace: dict = Depends(get_workspace_or_404),
    _: object = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    doc = await asset_service.get_asset(db, workspace["_id"], asset_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    await get_vector_store().delete_asset(workspace["vector_namespace"], asset_id)
    await get_storage().delete_prefix(f"{workspace['_id']}/{asset_id}")
    await asset_service.delete_asset_record(db, doc)
