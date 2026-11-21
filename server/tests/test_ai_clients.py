"""The one shared Claude client and the one shared OpenAI client: explicit
timeouts, no SDK retries (a retry is a second billed call). No network: the
clients are only constructed, never used."""
from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from app.config import settings
from app.services import ai_clients, claude_calls
from app.services.ai_service import GenerationService
from app.services.brand_extract_service import BrandExtractService


@pytest.fixture
def dummy_keys(monkeypatch):
    """A built client needs a key; CI runs with empty ones. Use a dummy (never a real
    key) and start and end with no cached clients."""
    monkeypatch.setattr(settings, "anthropic_api_key", SecretStr("sk-ant-dummy-not-real"))
    monkeypatch.setattr(settings, "openai_api_key", SecretStr("sk-dummy-not-real"))
    ai_clients.get_anthropic.cache_clear()
    ai_clients.get_openai.cache_clear()
    yield
    ai_clients.get_anthropic.cache_clear()
    ai_clients.get_openai.cache_clear()


def test_one_shared_anthropic_client_with_no_retries(dummy_keys):
    client = ai_clients.get_anthropic()
    assert client is ai_clients.get_anthropic()
    assert client.max_retries == 0
    assert client.timeout.read == settings.ai_request_timeout_s and client.timeout.connect == 5.0


def test_the_services_use_the_shared_client(dummy_keys):
    assert GenerationService().client is ai_clients.get_anthropic()
    assert BrandExtractService().client is ai_clients.get_anthropic()


def test_openai_client_has_no_retries_and_a_short_timeout(dummy_keys):
    client = ai_clients.get_openai()
    assert client is ai_clients.get_openai()
    assert client.max_retries == 0 and client.timeout == settings.embedding_timeout_s


def test_stream_timeout_is_a_short_read_with_a_short_connect():
    timeout = ai_clients.stream_timeout()
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read == settings.ai_stream_read_timeout_s
    assert timeout.connect == 5.0


def test_requests_carry_no_server_side_fallback():
    opts = claude_calls.request_options()
    assert "betas" not in opts and "fallbacks" not in opts


@pytest.mark.asyncio
async def test_close_ai_clients_closes_and_clears_the_cache(dummy_keys):
    anthropic = ai_clients.get_anthropic()
    openai = ai_clients.get_openai()
    await ai_clients.close_ai_clients()
    assert ai_clients.get_anthropic.cache_info().currsize == 0
    assert ai_clients.get_openai.cache_info().currsize == 0
    assert anthropic.is_closed()
    assert openai.is_closed()
    # Closing with nothing cached is a no-op.
    await ai_clients.close_ai_clients()


def test_the_suite_blocks_real_network_calls_but_allows_mock_transports():
    with pytest.raises(AssertionError, match="real network call in a test"):
        httpx.Client().get("http://example.invalid/")
    mock = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    assert mock.get("http://example.invalid/").status_code == 200
