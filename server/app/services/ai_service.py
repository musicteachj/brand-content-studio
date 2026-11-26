"""Claude generation. Mirrors the EMS `ai_service.py` streaming pattern
(DECISIONS #5): async Anthropic client, stream, yield text deltas. The retrieval +
prompt assembly happens in the route; this service owns the model call and the
post-stream parsing. The request shape itself lives in `claude_calls` (DECISIONS #40).

Cards are two model calls (ARCHITECTURE gotcha #8): `stream_copy` streams natural
prose for the live typing effect, then `extract_card_fields` makes a structured-output
call (JSON matching the strict card schema) to get the typed fields + image
keywords, never parsed from the stream."""
from __future__ import annotations

import contextlib
import re
from collections.abc import AsyncGenerator
from typing import Any

from app.prompts.document import DOC_SECTIONS_TOOL
from app.prompts.image_card import CARD_FIELDS_TOOL
from app.services import claude_calls
from app.services.ai_clients import get_anthropic
from app.services.ai_ledger import LineRequest
from app.services.ai_meter import MeteredLine

# Ceilings, not targets: the prompts set length. They leave room for adaptive
# thinking, which counts toward max_tokens, and for Sonnet 5.x's tokenizer
# (about 30% more tokens for the same text than Sonnet 4.6).
MAX_TOKENS = 4000
TEMPLATE_FILL_MAX_TOKENS = 4000
CARD_COPY_MAX_TOKENS = 2000
CARD_FIELDS_MAX_TOKENS = 4000
DOC_COPY_MAX_TOKENS = 4000
DOC_SECTIONS_MAX_TOKENS = 4000
_HASHTAG_RE = re.compile(r"#\w[\w-]*")


class GenerationService:
    """Instantiated per-request via FastAPI `Depends()` (zero-arg), matching the
    EMS service convention. Every method takes the ledger line its route reserved
    (`claude_calls` settles it)."""

    def __init__(self) -> None:
        self.client = get_anthropic()

    async def stream_text(
        self, system: str, user: str, *, line: MeteredLine
    ) -> AsyncGenerator[str, None]:
        # `aclosing` in all three streams: closing this wrapper must close the inner
        # generator now, so the SDK stream is closed and the line settled before the
        # close returns, not whenever the event loop finalizes it.
        async with contextlib.aclosing(
            claude_calls.stream_text(
                self.client, system=system, user=user, max_tokens=MAX_TOKENS, line=line
            )
        ) as stream:
            async for text in stream:
                yield text

    async def stream_copy(
        self, system: str, user: str, *, line: MeteredLine
    ) -> AsyncGenerator[str, None]:
        """Stream short card copy as natural prose for the live typing effect."""
        async with contextlib.aclosing(
            claude_calls.stream_text(
                self.client, system=system, user=user, max_tokens=CARD_COPY_MAX_TOKENS, line=line
            )
        ) as stream:
            async for text in stream:
                yield text

    async def extract_card_fields(
        self, system: str, user: str, *, line: MeteredLine
    ) -> dict[str, Any]:
        """Structured-output call → typed card fields + suggested keywords, as JSON
        matching the strict card schema. Non-streaming: this is a short, final
        structured call, not the live-typing surface."""
        return await self._structured_call(
            system, user, CARD_FIELDS_TOOL, CARD_FIELDS_MAX_TOKENS, line
        )

    async def stream_document(
        self, system: str, user: str, *, line: MeteredLine
    ) -> AsyncGenerator[str, None]:
        """Stream a full document as natural prose for the live drafting preview.
        Larger budget than card copy: a one-pager is longer than a card."""
        async with contextlib.aclosing(
            claude_calls.stream_text(
                self.client, system=system, user=user, max_tokens=DOC_COPY_MAX_TOKENS, line=line
            )
        ) as stream:
            async for text in stream:
                yield text

    async def extract_document_sections(
        self, system: str, user: str, *, line: MeteredLine
    ) -> dict[str, Any]:
        """Structured-output call → the typed `DocumentModel` fields. Mirrors
        `extract_card_fields`: the structure is never parsed from the stream."""
        return await self._structured_call(
            system, user, DOC_SECTIONS_TOOL, DOC_SECTIONS_MAX_TOKENS, line
        )

    async def fill_template_values(
        self, system: str, user: str, tool: dict[str, Any], *, line: MeteredLine
    ) -> dict[str, Any]:
        """Structured output → a value per template placeholder. The tool
        schema is built per-template from its discovered field names (Phase 5)."""
        return await self._structured_call(system, user, tool, TEMPLATE_FILL_MAX_TOKENS, line)

    async def _structured_call(
        self, system: str, user: str, tool: dict[str, Any], max_tokens: int, line: MeteredLine
    ) -> dict[str, Any]:
        return await claude_calls.structured_call(
            self.client, system=system, content=user, tool=tool, max_tokens=max_tokens, line=line
        )


# Ledger reservations, one per method above, so a route can reserve before it streams.
# A second call's estimate is built from its prompt with an empty copy, caption, or draft,
# plus room for the whole first output (`extra_input_tokens` = the first call's cap).


def text_line(system: str, user: str, *, purpose: str = "text_post") -> LineRequest:
    return claude_calls.text_line(purpose, system=system, user=user, max_tokens=MAX_TOKENS)


def card_copy_line(system: str, user: str) -> LineRequest:
    return claude_calls.text_line(
        "card_copy", system=system, user=user, max_tokens=CARD_COPY_MAX_TOKENS
    )


def card_fields_line(
    system: str, user: str, *, after_max_tokens: int, purpose: str = "card_fields"
) -> LineRequest:
    return claude_calls.structured_line(
        purpose,
        system=system,
        content=user,
        tool=CARD_FIELDS_TOOL,
        max_tokens=CARD_FIELDS_MAX_TOKENS,
        extra_input_tokens=after_max_tokens,
    )


def document_copy_line(system: str, user: str) -> LineRequest:
    return claude_calls.text_line(
        "document_copy", system=system, user=user, max_tokens=DOC_COPY_MAX_TOKENS
    )


def document_sections_line(system: str, user: str) -> LineRequest:
    return claude_calls.structured_line(
        "document_sections",
        system=system,
        content=user,
        tool=DOC_SECTIONS_TOOL,
        max_tokens=DOC_SECTIONS_MAX_TOKENS,
        extra_input_tokens=DOC_COPY_MAX_TOKENS,
    )


def template_fill_line(
    system: str, user: str, tool: dict[str, Any], *, purpose: str = "template_fill"
) -> LineRequest:
    return claude_calls.structured_line(
        purpose, system=system, content=user, tool=tool, max_tokens=TEMPLATE_FILL_MAX_TOKENS
    )


def parse_post(text: str) -> dict:
    """Split a finished post into the persisted TextOutput shape. Hashtags are
    extracted (the brand style ends posts with them) but left in `post_text` as
    rendered."""
    post_text = text.strip()
    # De-dupe, preserve order.
    seen: set[str] = set()
    unique: list[str] = []
    for h in _HASHTAG_RE.findall(post_text):
        if h not in seen:
            seen.add(h)
            unique.append(h)
    return {
        "post_text": post_text,
        "hashtags": unique,
        "char_count": len(post_text),
    }


def build_card_output(template_id: str, extracted: dict) -> dict:
    """Shape the structured-output result into the persisted card `output` (DATA_MODEL.md).
    The image is null at stream end — it is selected client-side in parallel and
    attached via PATCH once the user picks one."""
    keywords = extracted.get("suggested_keywords") or []
    return {
        "template_id": template_id,
        "fields": {
            "eyebrow": (extracted.get("eyebrow") or "").strip(),
            "headline": (extracted.get("headline") or "").strip(),
            "body": (extracted.get("body") or "").strip(),
            "cta": (extracted.get("cta") or "").strip(),
            "hashtag": (extracted.get("hashtag") or "").strip(),
        },
        "image": None,
        "suggested_keywords": [str(k).strip() for k in keywords if str(k).strip()][:6],
    }


def build_post_pack_output(caption: str, template_id: str, extracted: dict) -> dict:
    """Shape a post_pack `output` (Phase 3): the LinkedIn caption (TextOutput
    shape) plus the matching card nested under `card` (CardOutput shape). The
    card image is null until attached via PATCH — which targets `output.card`."""
    return {
        **parse_post(caption),
        "card": build_card_output(template_id, extracted),
    }
