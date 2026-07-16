"""Generation routes. `/generate/text` streams a LinkedIn post over SSE:
`{text}` deltas → a terminal `{meta}` (retrieval debug payload + generation id)
→ `[DONE]`. The generation is persisted server-side at stream end.

Empty/thin corpus is blocked *before* Claude is called — never generate with no
brand context (ARCHITECTURE gotcha #10).

NOTE: no `from __future__ import annotations` here — it turns route annotations
into ForwardRefs that FastAPI can't resolve through slowapi's @limiter.limit
wrapper (bodies would 422). Keep annotations concrete in rate-limited routes."""
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_database
from app.models.generation import (
    CardGenerateRequest,
    Length,
    PostPackGenerateRequest,
    TextGenerateRequest,
)
from app.prompts import image_card, post_pack, text_post
from app.prompts.exemplars import build_exemplar_guidance
from app.rag.vector_store import get_vector_store
from app.services import generations_service, retrieval_service
from app.services.generation_service import (
    GenerationService,
    build_card_output,
    build_post_pack_output,
    parse_post,
)
from app.utils.dependencies import enforce_demo_generation_quota, get_workspace_or_404
from app.utils.errors import client_error
from app.utils.ratelimit import GENERATE_RATE_LIMIT, limiter

router = APIRouter()

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # disable proxy buffering so tokens flush live
}


@router.post("/text")
@limiter.limit(GENERATE_RATE_LIMIT)
async def generate_text(
    request: Request,
    payload: TextGenerateRequest,
    service: GenerationService = Depends(GenerationService),
    workspace: dict = Depends(get_workspace_or_404),
    _quota: None = Depends(enforce_demo_generation_quota),
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
    exemplar_guidance = build_exemplar_guidance(
        [e.get("style_note", "") for e in (brand_profile.get("exemplars") or [])]
    )

    async def event_stream() -> AsyncGenerator[str, None]:
        parts: list[str] = []
        try:
            result = await retrieval_service.retrieve(
                get_vector_store(), namespace, payload.brief, k=6
            )
            if not result.chunks:
                yield _frame({"error": "No brand context could be retrieved for this brief."})
                return

            system = text_post.build_system(voice_summary, exemplar_guidance)
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
            yield _frame({"error": client_error(exc, context="streamed generation")})
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=_SSE_HEADERS
    )


@router.post("/card")
@limiter.limit(GENERATE_RATE_LIMIT)
async def generate_card(
    request: Request,
    payload: CardGenerateRequest,
    service: GenerationService = Depends(GenerationService),
    workspace: dict = Depends(get_workspace_or_404),
    _quota: None = Depends(enforce_demo_generation_quota),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Stream card copy for the live typing effect, then resolve the structured
    fields + image keywords via a forced tool-use call (ARCHITECTURE gotcha #8).
    Frame shapes mirror /text: `{text}` deltas → terminal `{meta}` → `[DONE]`."""
    if int(workspace.get("ready_chunk_count", 0)) <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This workspace has no ingested brand assets yet. Ingest assets first.",
        )

    namespace = workspace["vector_namespace"]
    brand_profile = workspace.get("brand_profile") or {}
    voice_summary = brand_profile.get("voice_summary")
    exemplar_guidance = build_exemplar_guidance(
        [e.get("style_note", "") for e in (brand_profile.get("exemplars") or [])]
    )
    template_id = payload.template_id.value

    async def event_stream() -> AsyncGenerator[str, None]:
        parts: list[str] = []
        try:
            result = await retrieval_service.retrieve(
                get_vector_store(), namespace, payload.brief, k=6
            )
            if not result.chunks:
                yield _frame({"error": "No brand context could be retrieved for this brief."})
                return

            copy_system = image_card.build_copy_system(voice_summary, exemplar_guidance)
            copy_user = image_card.build_copy_user(
                payload.brief, payload.template_id, payload.tone, result.chunks
            )
            async for delta in service.stream_copy(copy_system, copy_user):
                parts.append(delta)
                yield _frame({"text": delta})

            copy = "".join(parts).strip()
            if not copy:
                yield _frame({"error": "The model returned an empty response. Try again."})
                return

            extracted = await service.extract_card_fields(
                image_card.build_fields_system(),
                image_card.build_fields_user(payload.brief, payload.template_id, copy),
            )
            output = build_card_output(template_id, extracted)

            doc = await generations_service.create_generation(
                db,
                workspace_oid=workspace["_id"],
                owner_oid=workspace["owner_id"],
                type="card",
                brief=payload.brief,
                status="complete",
                output=output,
                retrieved_chunk_ids=result.chunk_ids,
                retrieval_meta=result.meta,
            )
            yield _frame(
                {
                    "meta": {
                        "generation_id": str(doc["_id"]),
                        "template_id": template_id,
                        "fields": output["fields"],
                        "suggested_keywords": output["suggested_keywords"],
                        "retrieval": result.envelope(),
                    }
                }
            )
        except Exception as exc:  # surface to the client without crashing the stream
            yield _frame({"error": client_error(exc, context="streamed generation")})
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=_SSE_HEADERS
    )


@router.post("/post")
@limiter.limit(GENERATE_RATE_LIMIT)
async def generate_post(
    request: Request,
    payload: PostPackGenerateRequest,
    service: GenerationService = Depends(GenerationService),
    workspace: dict = Depends(get_workspace_or_404),
    _quota: None = Depends(enforce_demo_generation_quota),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """The "LinkedIn Post" objective (Phase 3): stream the post caption for the
    live typing effect, then distill the matching card from that caption via a
    forced tool-use call. One brief, one retrieval → caption + card. Frame shapes
    mirror /text and /card: `{text}` deltas → terminal `{meta}` → `[DONE]`."""
    if int(workspace.get("ready_chunk_count", 0)) <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This workspace has no ingested brand assets yet. Ingest assets first.",
        )

    namespace = workspace["vector_namespace"]
    brand_profile = workspace.get("brand_profile") or {}
    voice_summary = brand_profile.get("voice_summary")
    exemplar_guidance = build_exemplar_guidance(
        [e.get("style_note", "") for e in (brand_profile.get("exemplars") or [])]
    )
    template_id = payload.template_id.value

    async def event_stream() -> AsyncGenerator[str, None]:
        parts: list[str] = []
        try:
            result = await retrieval_service.retrieve(
                get_vector_store(), namespace, payload.brief, k=6
            )
            if not result.chunks:
                yield _frame({"error": "No brand context could be retrieved for this brief."})
                return

            # 1) Stream the caption (a full LinkedIn post) for the live typing effect.
            caption_system = text_post.build_system(voice_summary, exemplar_guidance)
            caption_user = text_post.build_user(
                payload.brief, payload.tone, Length.medium, result.chunks
            )
            async for delta in service.stream_text(caption_system, caption_user):
                parts.append(delta)
                yield _frame({"text": delta})

            caption = "".join(parts).strip()
            if not caption:
                yield _frame({"error": "The model returned an empty response. Try again."})
                return

            # 2) Distill the matching card from the finished caption (tool-use).
            extracted = await service.extract_card_fields(
                post_pack.build_distill_system(),
                post_pack.build_distill_user(payload.brief, payload.template_id, caption),
            )
            output = build_post_pack_output(caption, template_id, extracted)

            doc = await generations_service.create_generation(
                db,
                workspace_oid=workspace["_id"],
                owner_oid=workspace["owner_id"],
                type="post_pack",
                brief=payload.brief,
                status="complete",
                output=output,
                retrieved_chunk_ids=result.chunk_ids,
                retrieval_meta=result.meta,
            )
            yield _frame(
                {
                    "meta": {
                        "generation_id": str(doc["_id"]),
                        "template_id": template_id,
                        "fields": output["card"]["fields"],
                        "suggested_keywords": output["card"]["suggested_keywords"],
                        "retrieval": result.envelope(),
                    }
                }
            )
        except Exception as exc:  # surface to the client without crashing the stream
            yield _frame({"error": client_error(exc, context="streamed generation")})
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=_SSE_HEADERS
    )


def _frame(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"
