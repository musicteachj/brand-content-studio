"""Template routes (Phase 5). Upload/list/delete branded .docx/.pptx templates,
optionally AI-draft their placeholder values, and render the filled file. Renders
are returned for immediate download, not persisted. The template's styling is
authoritative; we only swap `{{placeholder}}` text.

NOTE: no `from __future__ import annotations`: the AI routes use slowapi's
@limiter.limit, whose wrapper + ForwardRef annotations would 422 request bodies
(see generate.py)."""
import asyncio
import logging
import os

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_database
from app.limits import SOURCE_PARSE_TIMEOUT_S
from app.models.template import (
    TemplateAiFillRequest,
    TemplateAiFillResponse,
    TemplateRenderRequest,
    TemplateResponse,
)
from app.models.user import UserInDB
from app.prompts import template_fill
from app.services import template_service
from app.services.ai_service import GenerationService
from app.services.content_extraction import (
    NoExtractableTextError,
    UnsupportedSourceError,
    extract_document_text,
)
from app.services.storage_service import build_template_key, get_storage, safe_filename
from app.services.upload_service import SOURCE_POLICY, TEMPLATE_POLICY, read_upload
from app.utils.archives import UnsafeArchive
from app.utils.dependencies import (
    enforce_demo_generation_quota,
    get_workspace_or_404,
    require_not_demo,
)
from app.utils.ratelimit import GENERATE_RATE_LIMIT, limiter

logger = logging.getLogger(__name__)

router = APIRouter()

_MEDIA = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def upload_template(
    file: UploadFile,
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    data, filename, fmt = await read_upload(file, TEMPLATE_POLICY, default_name="template")
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
        ) from exc
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Reading this template timed out. Try a smaller or simpler file.",
        ) from None
    except template_service.TemplateHasLogic as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except Exception:  # noqa: BLE001 (a corrupt file must not 500)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Couldn't read this template. Is it a valid .docx or .pptx?",
        ) from None
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
@limiter.limit(GENERATE_RATE_LIMIT)
async def ai_fill_template(
    request: Request,
    template_id: str,
    payload: TemplateAiFillRequest,
    workspace: dict = Depends(get_workspace_or_404),
    service: GenerationService = Depends(GenerationService),
    _quota: None = Depends(enforce_demo_generation_quota),
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
    values = template_service.clamp_values(result, placeholders)
    return TemplateAiFillResponse(values=template_service.scrub_ai_values(values))


@router.post("/{template_id}/fill-from-document", response_model=TemplateAiFillResponse)
@limiter.limit(GENERATE_RATE_LIMIT)
async def fill_template_from_document(
    request: Request,
    template_id: str,
    file: UploadFile,
    workspace: dict = Depends(get_workspace_or_404),
    service: GenerationService = Depends(GenerationService),
    _quota: None = Depends(enforce_demo_generation_quota),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Draft each placeholder by mapping an uploaded document's content onto the
    template's fields. Generative + nothing persisted → allowed for the demo
    user; the source file is parsed in-memory and discarded."""
    doc = await template_service.get_template(db, workspace["_id"], template_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    data, filename, _ = await read_upload(file, SOURCE_POLICY, default_name="source")
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
            detail="Parsing the document timed out. Try a smaller or simpler file.",
        ) from None
    except (NoExtractableTextError, UnsupportedSourceError, UnsafeArchive) as exc:
        # Our own refusals, written for users; the client shows them verbatim.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except Exception as exc:  # noqa: BLE001 (a parser's own error text is internals)
        logger.info("fill-from-document: unreadable source %r: %s", filename, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Couldn't read that document. Is it a valid .docx, .pptx, .pdf, .txt, or .md file?",
        ) from exc
    tool = template_fill.build_fill_tool(placeholders)
    result = await service.fill_template_values(
        template_fill.build_fill_system(),
        template_fill.build_fill_user_from_content(content, placeholders),
        tool,
    )
    values = template_service.clamp_values(result, placeholders)
    return TemplateAiFillResponse(values=template_service.scrub_ai_values(values))


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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Template file missing"
        ) from None
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
        ) from exc
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Rendering this template timed out. Try a smaller or simpler file.",
        ) from None
    except template_service.TemplateHasLogic as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    out_name = safe_filename(f"{os.path.splitext(doc['name'])[0]}-filled.{fmt}")
    return Response(
        content=filled,
        media_type=_MEDIA[fmt],
        headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
    )
