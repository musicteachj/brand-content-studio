"""Client-safe error surfacing.

Raw `str(exc)` carries absolute server filesystem paths (FileNotFoundError from
storage), internal hostnames and ports (Mongo/Chroma connection errors) and
upstream API metadata (Anthropic/OpenAI status errors). None of that belongs in a
browser. Log the real thing, hand the client a correlation id instead.
"""
import logging
import uuid

logger = logging.getLogger(__name__)

GENERIC_ERROR = "Something went wrong. Please try again."


class UserFacingError(Exception):
    """An expected failure whose `message` is safe and useful to show as is (no
    internals in it), so it skips the redaction below. The SSE wrapper sends it as
    the error frame; an app exception handler returns it as `{"detail": message}`
    with `status_code`."""

    status_code = 422

    def __init__(self, message: str, *, log_detail: str | None = None) -> None:
        super().__init__(log_detail or message)
        self.message = message


def client_error(exc: Exception, *, context: str) -> str:
    """Log `exc` server-side; return a redacted message carrying a correlation id
    so a user report can be tied back to the log line."""
    ref = uuid.uuid4().hex[:12]
    logger.exception("%s failed [ref=%s]", context, ref, exc_info=exc)
    return f"{GENERIC_ERROR} (ref: {ref})"
