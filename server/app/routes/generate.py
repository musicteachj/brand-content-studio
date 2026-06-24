"""Generation routes. `/generate/text` streams a LinkedIn post over SSE:
`{text}` deltas → a terminal `{meta}` (retrieval debug payload + generation id)
→ `[DONE]`. The generation is persisted server-side at stream end.

Empty/thin corpus is blocked *before* Claude is called — never generate with no
brand context (ARCHITECTURE gotcha #10)."""
from __future__ import annotations

import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_database
from app.models.generation import TextGenerateRequest
from app.prompts import text_post
from app.rag.vector_store import get_vector_store
from app.services import generations_service, retrieval_service
from app.services.generation_service import GenerationService, parse_post
from app.utils.dependencies import get_workspace_or_404

router = APIRouter()

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # disable proxy buffering so tokens flush live
}


@router.post("/text")
async def generate_text(
    payload: TextGenerateRequest,
    service: GenerationService = Depends(),
    workspace: dict = Depends(get_workspace_or_404),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    if int(workspace.get("ready_chunk_count", 0)) <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This workspace has no ingested brand assets yet. Ingest assets first.",
        )

    namespace = workspace["vector_namespace"]
    brand_profile = workspace.get("brand_profile") or {}
    voice_summary = brand_profile.get("voice_summary")

    async def event_stream() -> AsyncGenerator[str, None]:
        parts: list[str] = []
        try:
            result = await retrieval_service.retrieve(
                get_vector_store(), namespace, payload.brief, k=6
            )
            if not result.chunks:
                yield _frame({"error": "No brand context could be retrieved for this brief."})
                return

            system = text_post.build_system(voice_summary)
            user = text_post.build_user(
                payload.brief, payload.tone, payload.length, result.chunks
            )
            async for delta in service.stream_text(system, user):
                parts.append(delta)
                yield _frame({"text": delta})

            if not "".join(parts).strip():
                yield _frame({"error": "The model returned an empty response. Try again."})
                return

            output = parse_post("".join(parts))
            doc = await generations_service.create_generation(
                db,
                workspace_oid=workspace["_id"],
                owner_oid=workspace["owner_id"],
                type="text",
                brief=payload.brief,
                status="complete",
                output=output,
                retrieved_chunk_ids=result.chunk_ids,
                retrieval_meta=result.meta,
            )
            yield _frame(
                {"meta": {"generation_id": str(doc["_id"]), "retrieval": result.envelope()}}
            )
        except Exception as exc:  # surface to the client without crashing the stream
            yield _frame({"error": str(exc)})
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=_SSE_HEADERS
    )


def _frame(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"
