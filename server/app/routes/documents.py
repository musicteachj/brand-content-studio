"""Document routes (Phase 2).

Two surfaces, mirroring the existing generate/serve split:
  - generate (`/api/workspaces/{id}/generate/document`) — SSE: stream the draft as
    prose, resolve the typed `DocumentModel` via tool-use, build the branded files,
    persist, then emit the format keys. Same `{text} → {meta} → [DONE]` frame shape
    as /text and /card; same hybrid retrieval and same empty-corpus block.
  - download (`/api/workspaces/{id}/generations/{gid}/download/{fmt}`) — auth-gated,
    ownership-checked file download. The storage key is rebuilt server-side from
    (workspace, generation, format), never trusted from the stored value.
"""
from __future__ import annotations

import json
from typing import AsyncGenerator

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response, StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_database
from app.models.generation import DocumentGenerateRequest
from app.prompts import document as document_prompt
from app.rag.vector_store import get_vector_store
from app.services import document_service, generations_service, retrieval_service
from app.services.generation_service import GenerationService
from app.services.storage_service import build_document_key, get_storage, safe_filename
from app.utils.dependencies import get_workspace_or_404

# Mounted at /api/workspaces/{workspace_id}/generate
router = APIRouter()
# Mounted at /api/workspaces/{workspace_id}/generations
download_router = APIRouter()

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # disable proxy buffering so tokens flush live
}

_DOC_MEDIA = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


@router.post("/document")
async def generate_document(
    payload: DocumentGenerateRequest,
    service: GenerationService = Depends(),
    workspace: dict = Depends(get_workspace_or_404),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Stream the document draft for the live preview, then resolve the structured
    model via tool-use, render the branded files, and emit their format keys."""
    if int(workspace.get("ready_chunk_count", 0)) <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This workspace has no ingested brand assets yet. Ingest assets first.",
        )

    namespace = workspace["vector_namespace"]
    brand_profile = workspace.get("brand_profile") or {}
    voice_summary = brand_profile.get("voice_summary")
    archetype = payload.archetype.value
    workspace_oid = workspace["_id"]
    workspace_id = str(workspace_oid)

    async def event_stream() -> AsyncGenerator[str, None]:
        parts: list[str] = []
        try:
            result = await retrieval_service.retrieve(
                get_vector_store(), namespace, payload.brief, k=6
            )
            if not result.chunks:
                yield _frame({"error": "No brand context could be retrieved for this brief."})
                return

            copy_system = document_prompt.build_copy_system(voice_summary)
            copy_user = document_prompt.build_copy_user(
                payload.brief, payload.archetype, payload.tone, result.chunks
            )
            async for delta in service.stream_document(copy_system, copy_user):
                parts.append(delta)
                yield _frame({"text": delta})

            draft = "".join(parts).strip()
            if not draft:
                yield _frame({"error": "The model returned an empty response. Try again."})
                return

            extracted = await service.extract_document_sections(
                document_prompt.build_fields_system(),
                document_prompt.build_fields_user(payload.brief, payload.archetype, draft),
            )
            output = document_service.build_document_output(archetype, extracted)

            # Build + store the branded files BEFORE persisting, so a render or
            # storage failure can't leave a "complete" generation with no files.
            # The id is pre-generated because the storage keys derive from it.
            generation_oid = ObjectId()
            generation_id = str(generation_oid)
            files = document_service.build_document_files(output["document"], brand_profile)
            storage = get_storage()
            formats: dict[str, dict] = {}
            for fmt, data in files.items():
                key = build_document_key(workspace_id, generation_id, fmt)
                await storage.save(key, data)
                formats[fmt] = {"storage_key": key}
            output["formats"] = formats

            await generations_service.create_generation(
                db,
                workspace_oid=workspace_oid,
                owner_oid=workspace["owner_id"],
                type="document",
                brief=payload.brief,
                status="complete",
                output=output,
                retrieved_chunk_ids=result.chunk_ids,
                retrieval_meta=result.meta,
                gen_id=generation_oid,
            )

            yield _frame(
                {
                    "meta": {
                        "generation_id": generation_id,
                        "archetype": archetype,
                        "document": output["document"],
                        "formats": formats,
                        "retrieval": result.envelope(),
                    }
                }
            )
        except Exception as exc:  # surface to the client without crashing the stream
            yield _frame({"error": str(exc)})
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=_SSE_HEADERS
    )


@download_router.get("/{generation_id}/download/{fmt}")
async def download_document(
    generation_id: str,
    fmt: str,
    workspace: dict = Depends(get_workspace_or_404),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Download a generated document file. Ownership is enforced by
    `get_workspace_or_404`; the storage key is rebuilt server-side, so a tampered
    stored key can never widen access (the path-traversal guard backs it up)."""
    if fmt not in _DOC_MEDIA:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown format.")

    doc = await generations_service.get_generation(db, workspace["_id"], generation_id)
    if not doc or doc.get("type") != "document":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    formats = (doc.get("output") or {}).get("formats") or {}
    if fmt not in formats:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="This format was not generated."
        )

    key = build_document_key(str(workspace["_id"]), generation_id, fmt)
    try:
        data = await get_storage().read(key)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    archetype = (doc.get("output") or {}).get("document", {}).get("archetype") or "document"
    filename = safe_filename(f"{archetype}.{fmt}")
    return Response(
        content=data,
        media_type=_DOC_MEDIA[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _frame(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"
