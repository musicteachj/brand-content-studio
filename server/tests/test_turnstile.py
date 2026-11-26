"""Cloudflare Turnstile verification. Every siteverify answer here comes from an
httpx.MockTransport; the suite's network guard fails any real request."""
import httpx
import pytest
from pydantic import SecretStr

from app.config import (
    TURNSTILE_FAIL_SECRET,
    TURNSTILE_PASS_SECRET,
    TURNSTILE_SPENT_SECRET,
    Settings,
)
from app.services import turnstile
from app.services.turnstile import (
    ACTION,
    DUMMY_TOKEN,
    SITEVERIFY_URL,
    CloudflareVerifier,
    TestKeyVerifier,
    Verdict,
    build_verifier,
)

HOST = "folio.example.com"


def _verifier(handler) -> tuple[CloudflareVerifier, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(record))
    return CloudflareVerifier("real-secret", HOST, client=client), seen


def _answer(body: dict, status: int = 200):
    return lambda request: httpx.Response(status, json=body)


async def test_a_token_passes_only_with_the_right_hostname_and_action():
    verifier, seen = _verifier(_answer({"success": True, "hostname": HOST, "action": ACTION}))
    assert await verifier.verify("tok", "203.0.113.9") is Verdict.PASSED
    assert ACTION == "demo-start"
    assert len(seen) == 1
    assert str(seen[0].url) == SITEVERIFY_URL
    form = dict(httpx.QueryParams(seen[0].content.decode()))
    assert form["secret"] == "real-secret"
    assert form["response"] == "tok"
    assert form["remoteip"] == "203.0.113.9"
    assert form["idempotency_key"]


@pytest.mark.parametrize(
    "body",
    [
        {"success": True, "hostname": "evil.example.com", "action": ACTION},
        {"success": True, "hostname": HOST, "action": "some-other-widget"},
        {"success": True, "hostname": HOST},
        {"success": False, "hostname": HOST, "action": ACTION, "error-codes": ["invalid-input-response"]},
        {"success": "true", "hostname": HOST, "action": ACTION},
    ],
)
async def test_a_wrong_hostname_or_action_fails(body):
    verifier, _ = _verifier(_answer(body))
    assert await verifier.verify("tok", None) is Verdict.FAILED


def _network_error(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down", request=request)


@pytest.mark.parametrize(
    "handler",
    [
        _answer({"success": False, "error-codes": ["internal-error"]}),
        _answer({"success": True, "hostname": HOST, "action": ACTION}, status=500),
        lambda request: httpx.Response(200, content=b"not json"),
        _network_error,
        _answer({"success": False, "error-codes": ["invalid-input-secret"]}),
    ],
    ids=["internal-error", "http-500", "unreadable-json", "network-error", "invalid-input-secret"],
)
async def test_cloudflare_trouble_is_unavailable(handler):
    verifier, _ = _verifier(handler)
    assert await verifier.verify("tok", None) is Verdict.UNAVAILABLE


async def test_an_empty_token_fails_without_a_request():
    verifier, seen = _verifier(_answer({"success": True, "hostname": HOST, "action": ACTION}))
    assert await verifier.verify("", "203.0.113.9") is Verdict.FAILED
    assert seen == []


async def test_the_test_secrets_are_answered_locally():
    # No transport at all: a request would fail the network guard.
    assert await TestKeyVerifier(TURNSTILE_PASS_SECRET).verify(DUMMY_TOKEN, None) is Verdict.PASSED
    assert await TestKeyVerifier(TURNSTILE_FAIL_SECRET).verify(DUMMY_TOKEN, None) is Verdict.FAILED
    assert await TestKeyVerifier(TURNSTILE_SPENT_SECRET).verify(DUMMY_TOKEN, None) is Verdict.FAILED
    assert await TestKeyVerifier(TURNSTILE_PASS_SECRET).verify("another-token", None) is Verdict.FAILED
    assert DUMMY_TOKEN == "XXXX.DUMMY.TOKEN.XXXX"


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


async def test_build_picks_the_local_verifier_only_for_test_secrets():
    for secret in (TURNSTILE_PASS_SECRET, TURNSTILE_FAIL_SECRET, TURNSTILE_SPENT_SECRET):
        built = build_verifier(_settings(turnstile_site_key="site", turnstile_secret_key=SecretStr(secret)))
        assert isinstance(built, TestKeyVerifier)
    # Blank keys outside production are Cloudflare's always-pass test pair.
    assert isinstance(build_verifier(_settings()), TestKeyVerifier)
    real = build_verifier(
        _settings(
            turnstile_site_key="0x4AAAAAAA-real",
            turnstile_secret_key=SecretStr("0x4AAAAAAA-real-secret"),
            app_origin="https://folio.example.com",
        )
    )
    assert isinstance(real, CloudflareVerifier)
    assert real._hostname == "folio.example.com"
    await real.aclose()


def test_the_dependency_is_cached():
    turnstile.reset_turnstile_verifier()
    try:
        assert turnstile.get_turnstile_verifier() is turnstile.get_turnstile_verifier()
    finally:
        turnstile.reset_turnstile_verifier()


def test_the_test_values_match_cloudflares_testing_page():
    from app.config import TURNSTILE_TEST_SITE_KEY

    assert TURNSTILE_TEST_SITE_KEY == "1x00000000000000000000AA"
    assert TURNSTILE_PASS_SECRET == "1x0000000000000000000000000000000AA"
    assert TURNSTILE_FAIL_SECRET == "2x0000000000000000000000000000000AA"
    assert TURNSTILE_SPENT_SECRET == "3x0000000000000000000000000000000AA"
