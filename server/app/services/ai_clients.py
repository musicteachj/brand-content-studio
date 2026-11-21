"""The one Claude client and the one OpenAI client in the process.

Both are built once and shared, so connections are pooled and the settings below
apply everywhere. The SDKs retry failed requests by default; here they never do
(`max_retries=0`), because a retry is a second billed call that nothing would
count. Timeouts are explicit so a stalled provider can't hold a request open."""
from __future__ import annotations

from functools import lru_cache

import httpx
from anthropic import AsyncAnthropic
from openai import OpenAI

from app.config import settings

CONNECT_TIMEOUT_S = 5.0


@lru_cache(maxsize=1)
def get_anthropic() -> AsyncAnthropic:
    return AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        max_retries=0,
        timeout=httpx.Timeout(settings.ai_request_timeout_s, connect=CONNECT_TIMEOUT_S),
    )


@lru_cache(maxsize=1)
def get_openai() -> OpenAI:
    return OpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        max_retries=0,
        timeout=settings.embedding_timeout_s,
    )


def stream_timeout() -> httpx.Timeout:
    """Per-request timeout for a streamed call: the read timeout is the longest
    silence allowed between chunks, not a cap on the whole stream."""
    return httpx.Timeout(settings.ai_stream_read_timeout_s, connect=CONNECT_TIMEOUT_S)


async def close_ai_clients() -> None:
    """Close whichever clients were created, then forget them (shutdown)."""
    if get_anthropic.cache_info().currsize:
        await get_anthropic().close()
    if get_openai.cache_info().currsize:
        get_openai().close()
    get_anthropic.cache_clear()
    get_openai.cache_clear()
