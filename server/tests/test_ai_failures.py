"""Which Claude failures cost nothing (settle to $0) and which keep the reservation, and
which ones mean the provider is out (friendly copy) rather than a bug. Built from real SDK
error classes; no network."""
from __future__ import annotations

import anthropic
import httpx
import pytest

from app.services.ai_failures import (
    Billing,
    classify_anthropic_error,
    is_provider_outage,
    is_usage_limit_message,
)

REQ = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _body(error_type: str, message: str) -> dict:
    return {"type": "error", "error": {"type": error_type, "message": message}}


def auth_401() -> anthropic.APIStatusError:
    return anthropic.AuthenticationError(
        "x", response=httpx.Response(401, request=REQ), body=_body("authentication_error", "invalid x-api-key")
    )


def permission_403() -> anthropic.APIStatusError:
    return anthropic.PermissionDeniedError(
        "x", response=httpx.Response(403, request=REQ), body=_body("permission_error", "no access")
    )


def status_402() -> anthropic.APIStatusError:
    return anthropic.APIStatusError(
        "x", response=httpx.Response(402, request=REQ), body=_body("billing_error", "payment required")
    )


def bad_request_400(message: str) -> anthropic.APIStatusError:
    return anthropic.BadRequestError(
        "x", response=httpx.Response(400, request=REQ), body=_body("invalid_request_error", message)
    )


def rate_limit_429(*, body: object) -> anthropic.APIStatusError:
    return anthropic.RateLimitError("x", response=httpx.Response(429, request=REQ), body=body)


def overloaded_529() -> anthropic.APIStatusError:
    return anthropic.OverloadedError(
        "x", response=httpx.Response(529, request=REQ), body=_body("overloaded_error", "Overloaded")
    )


def server_500() -> anthropic.APIStatusError:
    return anthropic.InternalServerError(
        "x", response=httpx.Response(500, request=REQ), body=_body("api_error", "Internal error")
    )


def overloaded_mid_stream() -> anthropic.APIStatusError:
    # The SDK raises a streamed `error` event with the stream's own 200 response.
    return anthropic.APIStatusError(
        "x", response=httpx.Response(200, request=REQ), body=_body("overloaded_error", "Overloaded")
    )


def timeout_error() -> anthropic.APIError:
    return anthropic.APITimeoutError(request=REQ)


def connection_error() -> anthropic.APIError:
    return anthropic.APIConnectionError(request=REQ)


WORKSPACE_LIMIT = "You have reached your specified workspace API usage limits. You will regain access on 2026-12-01."
ORG_LIMIT = "You have reached your specified organization API usage limits. You will regain access on 2026-12-01."
CREDIT_LOW = "Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing."

UNBILLED = [
    auth_401(),
    permission_403(),
    status_402(),
    bad_request_400(WORKSPACE_LIMIT),
    bad_request_400(ORG_LIMIT),
    bad_request_400(CREDIT_LOW),
    rate_limit_429(body=_body("rate_limit_error", "enforced_spend_limit_reached")),
    # Shared rule update 2026-11-19: any 429 is rejected before work is done.
    rate_limit_429(body={}),
]


@pytest.mark.parametrize("exc", UNBILLED)
def test_known_unbilled_failures(exc):
    assert classify_anthropic_error(exc, output_started=False) is Billing.UNBILLED


def test_overloaded_is_unbilled_only_before_output():
    # "Output" is any content event, thinking included (stream_text sets the flag).
    assert classify_anthropic_error(overloaded_529(), output_started=False) is Billing.UNBILLED
    assert classify_anthropic_error(overloaded_529(), output_started=True) is Billing.BILLED_OR_UNKNOWN
    assert classify_anthropic_error(overloaded_mid_stream(), output_started=False) is Billing.UNBILLED
    assert classify_anthropic_error(overloaded_mid_stream(), output_started=True) is Billing.BILLED_OR_UNKNOWN


@pytest.mark.parametrize(
    "exc",
    [timeout_error(), connection_error(), bad_request_400("invalid model"), server_500(), httpx.ReadTimeout("x")],
)
def test_everything_else_keeps_the_reservation(exc):
    assert classify_anthropic_error(exc, output_started=False) is Billing.BILLED_OR_UNKNOWN


@pytest.mark.parametrize(
    "message, expected",
    [
        (WORKSPACE_LIMIT, True),
        (ORG_LIMIT, True),
        ("You have reached your specified API usage limits.", True),
        ("you have reached your specified workspace api usage limits", True),
        (CREDIT_LOW, True),
        ("invalid model: claude-x", False),
        ("Please note: You have reached your specified API usage limits", False),
    ],
)
def test_usage_limit_messages(message, expected):
    assert is_usage_limit_message(message) is expected


@pytest.mark.parametrize(
    "exc",
    [*UNBILLED, overloaded_529(), overloaded_mid_stream(), server_500(), timeout_error(),
     connection_error(), httpx.ReadTimeout("x"), httpx.RemoteProtocolError("x")],
)
def test_provider_outages(exc):
    assert is_provider_outage(exc) is True


@pytest.mark.parametrize(
    "exc", [bad_request_400("invalid model"), ValueError("x"), RuntimeError("cap")]
)
def test_our_own_bugs_are_not_outages(exc):
    assert is_provider_outage(exc) is False
