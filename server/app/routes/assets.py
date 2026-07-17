"""Asset routes — upload (202 + BackgroundTask ingestion), list, get, delete.

Uploads are untrusted: type + size are validated, the storage key is derived
server-side, and ingestion runs out-of-band so the request returns immediately
and the UI polls the status pill."""
from __future__ import annotations

from bson import ObjectId
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_database
from app.models.asset import AssetKind, AssetPage, AssetResponse
from app.rag.vector_store import get_vector_store
from app.services import asset_service
from app.services.ingestion_service import ingest_asset
from app.services.storage_service import build_storage_key, get_storage
from app.services.upload_service import ASSET_POLICY, read_upload
from app.utils.dependencies import get_workspace_or_404, require_not_demo

router = APIRouter()


@router.post("", response_model=AssetResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_asset(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    asset_kind: AssetKind = Form(...),
    workspace: dict = Depends(get_workspace_or_404),
    _: object = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    data, filename, content_type = await read_upload(file, ASSET_POLICY, default_name="upload")

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


@router.get("", response_model=AssetPage)
async def list_assets(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    workspace: dict = Depends(get_workspace_or_404),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    items, next_offset = await asset_service.list_assets(
        db, workspace["_id"], limit=limit, offset=offset
    )
    return AssetPage(items=items, next_offset=next_offset)


@router.post(
    "/{asset_id}/reingest", response_model=AssetResponse, status_code=status.HTTP_202_ACCEPTED
)
async def reingest_asset(
    asset_id: str,
    background_tasks: BackgroundTasks,
    workspace: dict = Depends(get_workspace_or_404),
    _: object = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Retry ingestion for an asset (typically one in `error`). Drops any prior
    vectors first so a re-parse can't orphan old chunks, resets to `processing`,
    and re-runs ingestion out of band."""
    doc = await asset_service.get_asset(db, workspace["_id"], asset_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    await get_vector_store().delete_asset(workspace["vector_namespace"], asset_id)
    updated = await asset_service.mark_processing(db, doc["_id"])
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    background_tasks.add_task(ingest_asset, asset_id, workspace["vector_namespace"])
    return await asset_service.asset_response(updated)


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
