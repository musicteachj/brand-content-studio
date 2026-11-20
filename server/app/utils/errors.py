"""Client-safe error surfacing.

Raw `str(exc)` carries absolute server filesystem paths (FileNotFoundError from
storage), internal hostnames and ports (Mongo/Chroma connection errors) and
upstream API metadata (Anthropic/OpenAI status errors). None of that belongs in a
browser. Log the real thing, hand the client a correlation id instead.
"""
import logging
import uuid
from typing import Literal

logger = logging.getLogger(__name__)

GENERIC_ERROR = "Something went wrong. Please try again."

LIVE_AI_PAUSED_COPY = (
    "Live generation is paused right now. Browse the ready-made examples to see what Folio makes."
)
VISITOR_ALLOWANCE_COPY = (
    "You've used this demo's live generations. Browse the ready-made examples, "
    "or start a new demo later."
)
LIVE_AI_UNAVAILABLE_COPY = (
    "Live generation isn't available right now. Browse the ready-made examples to see what "
    "Folio makes."
)


class UserFacingError(Exception):
    """An expected failure whose `message` is safe and useful to show as is (no
    internals in it), so it skips the redaction below. The SSE wrapper sends it as
    the error frame; an app exception handler returns it as `{"detail": message}`
    with `status_code`."""

    status_code = 422
    # A stable machine-readable code the client can branch on; sent only when set.
    code: str | None = None

    def __init__(self, message: str, *, log_detail: str | None = None) -> None:
        super().__init__(log_detail or message)
        self.message = message


def client_error(exc: Exception, *, context: str) -> str:
    """Log `exc` server-side; return a redacted message carrying a correlation id
    so a user report can be tied back to the log line."""
    ref = uuid.uuid4().hex[:12]
    logger.exception("%s failed [ref=%s]", context, ref, exc_info=exc)
    return f"{GENERIC_ERROR} (ref: {ref})"


class BudgetRefusal(UserFacingError):
    """The dollar ledger declined an AI action: live AI is off, today's or the month's
    budget is used up, or this visitor's allowance is. Friendly copy, HTTP 429."""

    status_code = 429

    def __init__(self, reason: Literal["off", "today", "month", "visitor"]) -> None:
        self.reason = reason
        if reason == "visitor":
            self.code = "visitor_allowance"
            message = VISITOR_ALLOWANCE_COPY
        else:
            self.code = "live_ai_paused"
            message = LIVE_AI_PAUSED_COPY
        super().__init__(message, log_detail=f"budget refusal: {reason}")


class LiveAIUnavailable(UserFacingError):
    """Live AI can't run (a provider or ledger fault), shown as friendly copy, HTTP 503.
    `log_detail` goes to the log only."""

    status_code = 503
    code = "live_ai_unavailable"

    def __init__(self, *, log_detail: str) -> None:
        super().__init__(LIVE_AI_UNAVAILABLE_COPY, log_detail=log_detail)
