"""Generation routes. `/generate/text` streams a LinkedIn post over SSE:
`{text}` deltas → a terminal `{meta}` (retrieval debug payload + generation id)
→ `[DONE]`. The generation is persisted server-side at stream end.

Empty/thin corpus is blocked *before* Claude is called — never generate with no
brand context (ARCHITECTURE gotcha #10). The SSE plumbing (framing, the redacted
error frame, the terminal `[DONE]`) lives in `utils/sse.py`; each route provides
only a domain event generator that yields `{"text"|"error"|"meta": ...}` dicts.

NOTE: no `from __future__ import annotations` here — it turns route annotations
into ForwardRefs that FastAPI can't resolve through slowapi's @limiter.limit
wrapper (bodies would 422). Keep annotations concrete in rate-limited routes."""
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_database
from app.models.generation import (
    CardGenerateRequest,
    Length,
    PostPackGenerateRequest,
    TextGenerateRequest,
)
from app.prompts import image_card, post_pack, text_post
from app.prompts.exemplars import build_brand_context
from app.rag.vector_store import get_vector_store
from app.services import generations_service, retrieval_service
from app.services.ai_service import (
    GenerationService,
    build_card_output,
    build_post_pack_output,
    parse_post,
)
from app.utils.dependencies import (
    enforce_demo_generation_quota,
    ensure_ready_corpus,
    get_workspace_or_404,
)
from app.utils.ratelimit import GENERATE_RATE_LIMIT, limiter
from app.utils.sse import sse_response

router = APIRouter()

_STREAM_CONTEXT = "streamed generation"


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
    ensure_ready_corpus(workspace)
    namespace, _, voice_summary, exemplar_guidance = build_brand_context(workspace)

    async def produce() -> AsyncGenerator[dict, None]:
        parts: list[str] = []
        result = await retrieval_service.retrieve(get_vector_store(), namespace, payload.brief, k=6)
        if not result.chunks:
            yield {"error": "No brand context could be retrieved for this brief."}
            return

        system = text_post.build_system(voice_summary, exemplar_guidance)
        user = text_post.build_user(payload.brief, payload.tone, payload.length, result.chunks)
        async for delta in service.stream_text(system, user):
            parts.append(delta)
            yield {"text": delta}

        if not "".join(parts).strip():
            yield {"error": "The model returned an empty response. Try again."}
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
        yield {"meta": {"generation_id": str(doc["_id"]), "retrieval": result.envelope()}}

    return sse_response(produce(), context=_STREAM_CONTEXT)


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
    ensure_ready_corpus(workspace)
    namespace, _, voice_summary, exemplar_guidance = build_brand_context(workspace)
    template_id = payload.template_id.value

    async def produce() -> AsyncGenerator[dict, None]:
        parts: list[str] = []
        result = await retrieval_service.retrieve(get_vector_store(), namespace, payload.brief, k=6)
        if not result.chunks:
            yield {"error": "No brand context could be retrieved for this brief."}
            return

        copy_system = image_card.build_copy_system(voice_summary, exemplar_guidance)
        copy_user = image_card.build_copy_user(
            payload.brief, payload.template_id, payload.tone, result.chunks
        )
        async for delta in service.stream_copy(copy_system, copy_user):
            parts.append(delta)
            yield {"text": delta}

        copy = "".join(parts).strip()
        if not copy:
            yield {"error": "The model returned an empty response. Try again."}
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
        yield {
            "meta": {
                "generation_id": str(doc["_id"]),
                "template_id": template_id,
                "fields": output["fields"],
                "suggested_keywords": output["suggested_keywords"],
                "retrieval": result.envelope(),
            }
        }

    return sse_response(produce(), context=_STREAM_CONTEXT)


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
    ensure_ready_corpus(workspace)
    namespace, _, voice_summary, exemplar_guidance = build_brand_context(workspace)
    template_id = payload.template_id.value

    async def produce() -> AsyncGenerator[dict, None]:
        parts: list[str] = []
        result = await retrieval_service.retrieve(get_vector_store(), namespace, payload.brief, k=6)
        if not result.chunks:
            yield {"error": "No brand context could be retrieved for this brief."}
            return

        # 1) Stream the caption (a full LinkedIn post) for the live typing effect.
        caption_system = text_post.build_system(voice_summary, exemplar_guidance)
        caption_user = text_post.build_user(payload.brief, payload.tone, Length.medium, result.chunks)
        async for delta in service.stream_text(caption_system, caption_user):
            parts.append(delta)
            yield {"text": delta}

        caption = "".join(parts).strip()
        if not caption:
            yield {"error": "The model returned an empty response. Try again."}
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
        yield {
            "meta": {
                "generation_id": str(doc["_id"]),
                "template_id": template_id,
                "fields": output["card"]["fields"],
                "suggested_keywords": output["card"]["suggested_keywords"],
                "retrieval": result.envelope(),
            }
        }

    return sse_response(produce(), context=_STREAM_CONTEXT)
