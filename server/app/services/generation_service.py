"""Claude text-post generation. Mirrors the EMS `ai_service.py` streaming
pattern (DECISIONS #5) — async Anthropic client, `messages.stream`, yield text
deltas. The retrieval + prompt assembly happens in the route; this service owns
the model call and the post-stream parsing."""
from __future__ import annotations

import re
from typing import AsyncGenerator

from anthropic import AsyncAnthropic

from app.config import settings

MAX_TOKENS = 1500
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
