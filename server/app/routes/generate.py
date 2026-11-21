"""Generation routes. `/generate/text` streams a LinkedIn post over SSE:
`{text}` deltas → a terminal `{meta}` (retrieval debug payload + generation id)
→ `[DONE]`. The generation is persisted server-side at stream end.

Empty/thin corpus is blocked *before* Claude is called: never generate with no
brand context (ARCHITECTURE gotcha #10). Before the SSE response starts, each route
retrieves (a 409 when nothing matches), builds every prompt, and reserves every model
call it will make in the AI dollar ledger, so a refusal is a plain HTTP error, never a
frame mid-stream. Inside the stream each call settles its own line, and `finalize`
releases a call that never ran (an empty first output) or keeps the reservation of one
that was cut off. The SSE plumbing (framing, the redacted error frame, the terminal
`[DONE]`) lives in `utils/sse.py`; each route provides only a domain event generator
that yields `{"text"|"error"|"meta": ...}` dicts.

NOTE: no `from __future__ import annotations` here — it turns route annotations
into ForwardRefs that FastAPI can't resolve through slowapi's @limiter.limit
wrapper (bodies would 422). Keep annotations concrete in rate-limited routes."""
from collections.abc import AsyncGenerator
from contextlib import aclosing

from fastapi import APIRouter, Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_database
from app.models.generation import (
    CardGenerateRequest,
    Length,
    PostPackGenerateRequest,
    TextGenerateRequest,
)
from app.models.user import UserInDB
from app.prompts import image_card, post_pack, text_post
from app.prompts.exemplars import build_brand_context
from app.rag.vector_store import get_vector_store
from app.services import generations_service
from app.services.ai_meter import reserve_action
from app.services.ai_service import (
    CARD_COPY_MAX_TOKENS,
    MAX_TOKENS,
    GenerationService,
    build_card_output,
    build_post_pack_output,
    card_copy_line,
    card_fields_line,
    parse_post,
    text_line,
)
from app.utils.dependencies import (
    ensure_ready_corpus,
    get_current_user,
    get_workspace_or_404,
    ledger_visitor_id,
    retrieve_context_or_409,
)
from app.utils.ratelimit import GENERATE_RATE_LIMIT, limiter
from app.utils.sse import sse_response

router = APIRouter()

_STREAM_CONTEXT = "streamed generation"
_EMPTY_REPLY = "The model returned an empty response. Try again."


@router.post("/text")
@limiter.limit(GENERATE_RATE_LIMIT)
async def generate_text(
    request: Request,
    payload: TextGenerateRequest,
    service: GenerationService = Depends(GenerationService),
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    ensure_ready_corpus(workspace)
    namespace, _, voice_summary, exemplar_guidance = build_brand_context(workspace)
    result = await retrieve_context_or_409(
        get_vector_store(),
        namespace,
        payload.brief,
        db=db,
        visitor_id=ledger_visitor_id(current_user),
    )
    system = text_post.build_system(voice_summary, exemplar_guidance)
    user = text_post.build_user(payload.brief, payload.tone, payload.length, result.chunks)
    action = await reserve_action(
        db, [text_line(system, user)], visitor_id=ledger_visitor_id(current_user)
    )

    async def produce() -> AsyncGenerator[dict, None]:
        try:
            parts: list[str] = []
            # aclosing: a disconnect at a yield closes the model stream at once, first.
            async with aclosing(service.stream_text(system, user, line=action.lines[0])) as stream:
                async for delta in stream:
                    parts.append(delta)
                    yield {"text": delta}

            if not "".join(parts).strip():
                yield {"error": _EMPTY_REPLY}
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
                session_id=current_user.session_id,
                expires_at=current_user.session_expires_at,
            )
            yield {"meta": {"generation_id": str(doc["_id"]), "retrieval": result.envelope()}}
        finally:
            await action.finalize()

    return sse_response(produce(), context=_STREAM_CONTEXT, on_close=action.finalize)


@router.post("/card")
@limiter.limit(GENERATE_RATE_LIMIT)
async def generate_card(
    request: Request,
    payload: CardGenerateRequest,
    service: GenerationService = Depends(GenerationService),
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Stream card copy for the live typing effect, then resolve the structured
    fields + image keywords via a structured-output call (ARCHITECTURE gotcha #8).
    Frame shapes mirror /text: `{text}` deltas → terminal `{meta}` → `[DONE]`."""
    ensure_ready_corpus(workspace)
    namespace, _, voice_summary, exemplar_guidance = build_brand_context(workspace)
    template_id = payload.template_id.value
    result = await retrieve_context_or_409(
        get_vector_store(),
        namespace,
        payload.brief,
        db=db,
        visitor_id=ledger_visitor_id(current_user),
    )
    copy_system = image_card.build_copy_system(voice_summary, exemplar_guidance)
    copy_user = image_card.build_copy_user(
        payload.brief, payload.template_id, payload.tone, result.chunks
    )
    fields_system = image_card.build_fields_system()
    action = await reserve_action(
        db,
        [
            card_copy_line(copy_system, copy_user),
            card_fields_line(
                fields_system,
                image_card.build_fields_user(payload.brief, payload.template_id, ""),
                after_max_tokens=CARD_COPY_MAX_TOKENS,
            ),
        ],
        visitor_id=ledger_visitor_id(current_user),
    )

    async def produce() -> AsyncGenerator[dict, None]:
        try:
            parts: list[str] = []
            async with aclosing(
                service.stream_copy(copy_system, copy_user, line=action.lines[0])
            ) as stream:
                async for delta in stream:
                    parts.append(delta)
                    yield {"text": delta}

            copy = "".join(parts).strip()
            if not copy:
                yield {"error": _EMPTY_REPLY}
                return

            extracted = await service.extract_card_fields(
                fields_system,
                image_card.build_fields_user(payload.brief, payload.template_id, copy),
                line=action.lines[1],
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
                session_id=current_user.session_id,
                expires_at=current_user.session_expires_at,
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
        finally:
            await action.finalize()

    return sse_response(produce(), context=_STREAM_CONTEXT, on_close=action.finalize)


@router.post("/post")
@limiter.limit(GENERATE_RATE_LIMIT)
async def generate_post(
    request: Request,
    payload: PostPackGenerateRequest,
    service: GenerationService = Depends(GenerationService),
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """The "LinkedIn Post" objective (Phase 3): stream the post caption for the
    live typing effect, then distill the matching card from that caption via a
    structured-output call. One brief, one retrieval → caption + card. Frame shapes
    mirror /text and /card: `{text}` deltas → terminal `{meta}` → `[DONE]`."""
    ensure_ready_corpus(workspace)
    namespace, _, voice_summary, exemplar_guidance = build_brand_context(workspace)
    template_id = payload.template_id.value
    result = await retrieve_context_or_409(
        get_vector_store(),
        namespace,
        payload.brief,
        db=db,
        visitor_id=ledger_visitor_id(current_user),
    )
    caption_system = text_post.build_system(voice_summary, exemplar_guidance)
    caption_user = text_post.build_user(payload.brief, payload.tone, Length.medium, result.chunks)
    distill_system = post_pack.build_distill_system()
    action = await reserve_action(
        db,
        [
            text_line(caption_system, caption_user, purpose="post_caption"),
            card_fields_line(
                distill_system,
                post_pack.build_distill_user(payload.brief, payload.template_id, ""),
                after_max_tokens=MAX_TOKENS,
                purpose="post_card_fields",
            ),
        ],
        visitor_id=ledger_visitor_id(current_user),
    )

    async def produce() -> AsyncGenerator[dict, None]:
        try:
            parts: list[str] = []
            # 1) Stream the caption (a full LinkedIn post) for the live typing effect.
            async with aclosing(
                service.stream_text(caption_system, caption_user, line=action.lines[0])
            ) as stream:
                async for delta in stream:
                    parts.append(delta)
                    yield {"text": delta}

            caption = "".join(parts).strip()
            if not caption:
                yield {"error": _EMPTY_REPLY}
                return

            # 2) Distill the matching card from the finished caption (structured output).
            extracted = await service.extract_card_fields(
                distill_system,
                post_pack.build_distill_user(payload.brief, payload.template_id, caption),
                line=action.lines[1],
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
                session_id=current_user.session_id,
                expires_at=current_user.session_expires_at,
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
        finally:
            await action.finalize()

    return sse_response(produce(), context=_STREAM_CONTEXT, on_close=action.finalize)
