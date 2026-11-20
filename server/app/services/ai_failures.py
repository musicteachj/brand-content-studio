"""How a failed Claude call is billed, and whether it means the provider is out.

Settled to $0 (the request was rejected before any work was done): 401, 403, 402; a 400 for a
workspace or organization usage limit, or a credit balance too low; any 429, a plain rate limit
included (shared rule update 2026-11-19); and a 529 or overloaded error before any output
(thinking counts as output: it is billed even before any text arrives).
Everything else keeps its full reservation, because the call may have been billed.

A provider outage is shown to the visitor as friendly copy (`LiveAIUnavailable`) instead of the
redacted generic error; anything else (a 400 for a bad request) is our bug and is re-raised.
"""
from __future__ import annotations

import re
from enum import Enum

import anthropic
import httpx


class Billing(Enum):
    UNBILLED = "unbilled"
    BILLED_OR_UNKNOWN = "billed_or_unknown"


_USAGE_LIMIT = re.compile(
    r"^You have reached your specified (workspace |organization )?API usage limits", re.IGNORECASE
)
_CREDIT_TOO_LOW = re.compile(r"credit balance is too low", re.IGNORECASE)

# Error types a stream can report in an `error` event, where the status code is the
# stream's own 200.
_OVERLOADED = "overloaded_error"
_OUTAGE_TYPES = frozenset({_OVERLOADED, "api_error", "rate_limit_error"})


def is_usage_limit_message(message: str) -> bool:
    message = message.strip()
    return bool(_USAGE_LIMIT.match(message) or _CREDIT_TOO_LOW.search(message))


def _error_message(exc: anthropic.APIStatusError) -> str:
    body = exc.body
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return str(error["message"])
    return ""


def _is_usage_limit_400(exc: anthropic.APIStatusError) -> bool:
    return exc.status_code == 400 and is_usage_limit_message(_error_message(exc))


def _is_overloaded(exc: anthropic.APIStatusError) -> bool:
    return exc.status_code == 529 or exc.type == _OVERLOADED


def classify_anthropic_error(exc: BaseException, *, output_started: bool) -> Billing:
    if not isinstance(exc, anthropic.APIStatusError):
        # Timeouts, dropped connections, and anything unknown: the call may have run.
        return Billing.BILLED_OR_UNKNOWN
    if exc.status_code in (401, 402, 403, 429) or _is_usage_limit_400(exc):
        return Billing.UNBILLED
    if _is_overloaded(exc) and not output_started:
        return Billing.UNBILLED
    return Billing.BILLED_OR_UNKNOWN


def is_provider_outage(exc: BaseException) -> bool:
    if isinstance(exc, anthropic.APIConnectionError | httpx.TransportError):
        return True  # includes timeouts, which subclass both
    if not isinstance(exc, anthropic.APIStatusError):
        return False
    return (
        exc.status_code in (401, 402, 403, 429)
        or exc.status_code >= 500
        or _is_usage_limit_400(exc)
        or exc.type in _OUTAGE_TYPES
    )
