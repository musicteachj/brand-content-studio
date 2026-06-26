"""Claude generation. Mirrors the EMS `ai_service.py` streaming pattern
(DECISIONS #5) — async Anthropic client, `messages.stream`, yield text deltas.
The retrieval + prompt assembly happens in the route; this service owns the model
call and the post-stream parsing.

Cards are two model calls (ARCHITECTURE gotcha #8): `stream_copy` streams natural
prose for the live typing effect, then `extract_card_fields` makes a forced,
strict tool-use call to get the typed fields + image keywords — never parsed from
the stream."""
from __future__ import annotations

import re
from typing import Any, AsyncGenerator, cast

from anthropic import AsyncAnthropic
from anthropic.types import ToolChoiceToolParam, ToolParam

from app.config import settings
from app.prompts.image_card import CARD_FIELDS_TOOL

MAX_TOKENS = 1500
CARD_COPY_MAX_TOKENS = 600
CARD_FIELDS_MAX_TOKENS = 700
_HASHTAG_RE = re.compile(r"#\w[\w-]*")


class GenerationService:
    """Instantiated per-request via FastAPI `Depends()` (zero-arg), matching the
    EMS service convention."""

    def __init__(self) -> None:
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def stream_text(self, system: str, user: str) -> AsyncGenerator[str, None]:
        async with self.client.messages.stream(
            model=settings.ai_model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def stream_copy(self, system: str, user: str) -> AsyncGenerator[str, None]:
        """Stream short card copy as natural prose for the live typing effect."""
        async with self.client.messages.stream(
            model=settings.ai_model,
            max_tokens=CARD_COPY_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def extract_card_fields(self, system: str, user: str) -> dict[str, Any]:
        """Forced strict tool-use call → typed card fields + suggested keywords.

        `tool_choice` forces the single tool, so the response's first tool_use
        block carries the validated input. Non-streaming: this is a short, final
        structured call, not the live-typing surface."""
        message = await self.client.messages.create(
            model=settings.ai_model,
            max_tokens=CARD_FIELDS_MAX_TOKENS,
            system=system,
            tools=[cast(ToolParam, CARD_FIELDS_TOOL)],
            tool_choice=cast(
                ToolChoiceToolParam, {"type": "tool", "name": CARD_FIELDS_TOOL["name"]}
            ),
            messages=[{"role": "user", "content": user}],
        )
        for block in message.content:
            if block.type == "tool_use":
                return dict(block.input)  # type: ignore[arg-type]
        raise RuntimeError("Model did not return the card_fields tool call.")


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
    """Shape the tool-use result into the persisted card `output` (DATA_MODEL.md).
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
