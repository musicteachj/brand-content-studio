"""Template routes (Phase 5). Upload/list/delete branded .docx/.pptx templates,
optionally AI-draft their placeholder values, and render the filled file. Renders
are returned for immediate download — not persisted. The template's styling is
authoritative; we only swap `{{placeholder}}` text."""
from __future__ import annotations

import asyncio
import os

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_database
from app.models.template import (
    TemplateAiFillRequest,
    TemplateAiFillResponse,
    TemplateRenderRequest,
    TemplateResponse,
)
from app.models.user import UserInDB
from app.prompts import template_fill
from app.services import template_service
from app.services.content_extraction import extract_document_text
from app.utils.archives import UnsafeArchive
from app.services.generation_service import GenerationService
from app.services.storage_service import build_template_key, get_storage, safe_filename
from app.utils.dependencies import get_workspace_or_404, require_not_demo

router = APIRouter()

MAX_TEMPLATE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_SOURCE_BYTES = 10 * 1024 * 1024  # 10 MB
SOURCE_PARSE_TIMEOUT_S = 30
_SOURCE_EXTS = {".docx", ".pptx", ".pdf", ".txt", ".md", ".markdown"}
_FORMAT_BY_EXT = {".docx": "docx", ".pptx": "pptx"}
_MEDIA = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def _resolve_format(filename: str) -> str:
    fmt = _FORMAT_BY_EXT.get(os.path.splitext(filename)[1].lower())
    if not fmt:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported template. Upload a .docx or .pptx file.",
        )
    return fmt


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def upload_template(
    file: UploadFile,
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    filename = file.filename or "template"
    fmt = _resolve_format(filename)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file.")
    if len(data) > MAX_TEMPLATE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Template exceeds the {MAX_TEMPLATE_BYTES // (1024 * 1024)} MB limit.",
        )
    try:
        # Off the event loop under a timeout: the template is untrusted, and
        # docxtpl parses it as Jinja source (a nested `{% for %}` over range() is a
        # CPU bomb that would otherwise freeze the worker for every other user).
        placeholders = await asyncio.wait_for(
            asyncio.to_thread(template_service.discover_placeholders, data, fmt),
            SOURCE_PARSE_TIMEOUT_S,
        )
    except UnsafeArchive as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Reading this template timed out — try a smaller or simpler file.",
        )
    except Exception:  # noqa: BLE001 — a corrupt file must not 500
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Couldn't read this template — is it a valid .docx/.pptx?",
        )
    if len(placeholders) > template_service.MAX_PLACEHOLDERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Template has too many fields (max {template_service.MAX_PLACEHOLDERS}).",
        )

    workspace_oid = workspace["_id"]
    template_oid = ObjectId()
    clean_name = safe_filename(filename)
    storage_key = build_template_key(str(workspace_oid), str(template_oid), clean_name)
    await get_storage().save(storage_key, data)
    return await template_service.create_template(
        db,
        workspace_oid,
        workspace["owner_id"],
        template_oid=template_oid,
        name=clean_name,
        fmt=fmt,
        storage_key=storage_key,
        placeholders=placeholders,
    )


@router.get("", response_model=list[TemplateResponse])
async def list_templates(
    workspace: dict = Depends(get_workspace_or_404),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    return await template_service.list_templates(db, workspace["_id"])


@router.delete("/{template_id}", status_code=status.HTTP_200_OK)
async def delete_template(
    template_id: str,
    workspace: dict = Depends(get_workspace_or_404),
    _: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    doc = await template_service.get_template(db, workspace["_id"], template_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    await template_service.delete_template(db, doc)
    await get_storage().delete(doc["storage_key"])
    return {"deleted": True}


@router.post("/{template_id}/ai-fill", response_model=TemplateAiFillResponse)
async def ai_fill_template(
    template_id: str,
    payload: TemplateAiFillRequest,
    workspace: dict = Depends(get_workspace_or_404),
    service: GenerationService = Depends(GenerationService),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Draft a value for each placeholder from a brief (optional path). Generative,
    not a mutation → allowed for the demo user. Nothing is persisted."""
    doc = await template_service.get_template(db, workspace["_id"], template_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    placeholders = doc.get("placeholders") or []
    if not placeholders:
        return TemplateAiFillResponse(values={})
    tool = template_fill.build_fill_tool(placeholders)
    result = await service.fill_template_values(
        template_fill.build_fill_system(),
        template_fill.build_fill_user(payload.brief, placeholders),
        tool,
    )
    return TemplateAiFillResponse(values=template_service.clamp_values(result, placeholders))


@router.post("/{template_id}/fill-from-document", response_model=TemplateAiFillResponse)
async def fill_template_from_document(
    template_id: str,
    file: UploadFile,
    workspace: dict = Depends(get_workspace_or_404),
    service: GenerationService = Depends(GenerationService),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Draft each placeholder by mapping an uploaded document's content onto the
    template's fields. Generative + nothing persisted → allowed for the demo
    user; the source file is parsed in-memory and discarded."""
    doc = await template_service.get_template(db, workspace["_id"], template_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    filename = file.filename or "source"
    if os.path.splitext(filename)[1].lower() not in _SOURCE_EXTS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported document. Upload a .docx, .pptx, .pdf, .txt, or .md file.",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file.")
    if len(data) > MAX_SOURCE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Document exceeds the {MAX_SOURCE_BYTES // (1024 * 1024)} MB limit.",
        )
    placeholders = doc.get("placeholders") or []
    if not placeholders:
        return TemplateAiFillResponse(values={})
    try:
        content = await asyncio.wait_for(
            asyncio.to_thread(extract_document_text, data, filename), SOURCE_PARSE_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Parsing the document timed out — try a smaller or simpler file.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    tool = template_fill.build_fill_tool(placeholders)
    result = await service.fill_template_values(
        template_fill.build_fill_system(),
        template_fill.build_fill_user_from_content(content, placeholders),
        tool,
    )
    return TemplateAiFillResponse(values=template_service.clamp_values(result, placeholders))


@router.post("/{template_id}/render")
async def render_template(
    template_id: str,
    payload: TemplateRenderRequest,
    workspace: dict = Depends(get_workspace_or_404),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Fill the template with the given values and return the file for download.
    Ownership via the dependency; the template's storage key is rebuilt server-side."""
    doc = await template_service.get_template(db, workspace["_id"], template_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    fmt = doc["format"]
    key = build_template_key(str(workspace["_id"]), template_id, doc["name"])
    try:
        data = await get_storage().read(key)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template file missing")
    values = template_service.clamp_values(payload.values, doc.get("placeholders") or [])
    try:
        # Same reasoning as upload: the stored template is user-uploaded, and
        # render() hands it to Jinja. Keep the blocking render off the event loop.
        filled = await asyncio.wait_for(
            asyncio.to_thread(template_service.render, data, values, fmt),
            SOURCE_PARSE_TIMEOUT_S,
        )
    except UnsafeArchive as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Rendering this template timed out — try a smaller or simpler file.",
        )
    out_name = safe_filename(f"{os.path.splitext(doc['name'])[0]}-filled.{fmt}")
    return Response(
        content=filled,
        media_type=_MEDIA[fmt],
        headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
    )
