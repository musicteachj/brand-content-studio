"""Secrets in settings never print (they're SecretStr), the fail-closed JWT
secret check (SEC-06), and the API docs being off in production."""
import pytest
from pydantic import SecretStr, ValidationError

from app.config import DEFAULT_JWT_SECRET, Settings, settings

SECRETS = {
    "jwt_secret_key": "jwt-secret-value-that-is-long-enough-000",
    "anthropic_api_key": "sk-ant-test-secret",
    "openai_api_key": "sk-openai-test-secret",
    "unsplash_access_key": "unsplash-test-secret",
}


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **{**SECRETS, **overrides})


def test_secrets_never_appear_when_settings_are_printed():
    s = _settings()
    for text in (repr(s), str(s), f"{s}", repr(s.model_dump())):
        for value in SECRETS.values():
            assert value not in text


@pytest.mark.parametrize(
    "overrides",
    [
        {"csp_mode": "sometimes"},  # a field error
        {"environment": "production", "jwt_secret_key": "short"},  # the model-level check
    ],
)
def test_a_validation_error_doesnt_echo_any_input(overrides):
    # pydantic quotes the raw input (`input_value=`), even truncated, unless told not
    # to; at boot that input is every env setting, keys included.
    with pytest.raises(ValidationError) as exc:
        _settings(**overrides)
    text = str(exc.value)
    assert "input_value" not in text
    for value in SECRETS.values():
        assert value not in text and value[-12:] not in text


def test_the_raw_values_are_still_readable_where_they_are_used():
    s = _settings()
    assert s.anthropic_api_key.get_secret_value() == "sk-ant-test-secret"
    assert not Settings(_env_file=None, openai_api_key="").openai_api_key.get_secret_value()


def test_the_providers_get_the_raw_keys(monkeypatch):
    from app.rag.embeddings import OpenAIEmbedder
    from app.services.ai_service import GenerationService
    from app.services.brand_extract_service import BrandExtractService
    from app.services.unsplash_service import _require_key

    monkeypatch.setattr(settings, "anthropic_api_key", SecretStr("sk-ant-raw"))
    monkeypatch.setattr(settings, "openai_api_key", SecretStr("sk-openai-raw"))
    monkeypatch.setattr(settings, "unsplash_access_key", SecretStr("unsplash-raw"))
    assert GenerationService().client.api_key == "sk-ant-raw"
    assert BrandExtractService().client.api_key == "sk-ant-raw"
    assert OpenAIEmbedder()._client.api_key == "sk-openai-raw"
    assert _require_key() == "unsplash-raw"


def test_jwt_round_trip_uses_the_raw_secret(monkeypatch):
    import jwt

    from app.utils.security import create_access_token, decode_access_token

    monkeypatch.setattr(settings, "jwt_secret_key", SecretStr("x" * 40))
    token = create_access_token({"sub": "u1"})
    assert decode_access_token(token)["sub"] == "u1"
    jwt.decode(token, "x" * 40, algorithms=["HS256"])  # signed with the raw value


# --- SEC-06: fail closed in production ----------------------------------------
def test_production_rejects_the_shipped_jwt_secret():
    with pytest.raises(ValidationError, match="shipped default"):
        _settings(environment="production", jwt_secret_key=DEFAULT_JWT_SECRET)


def test_production_rejects_a_short_jwt_secret():
    with pytest.raises(ValidationError, match="at least 32"):
        _settings(environment="production", jwt_secret_key="short")


def test_production_accepts_a_long_jwt_secret_and_dev_accepts_the_default(monkeypatch):
    assert _settings(environment="production").environment == "production"
    # _env_file=None skips .env, but the process environment still applies (CI sets
    # JWT_SECRET_KEY), so clear it to see the shipped default.
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    assert Settings(_env_file=None, environment="development").jwt_secret_key.get_secret_value() == DEFAULT_JWT_SECRET


# --- API docs ----------------------------------------------------------------------
def test_api_docs_are_off_in_production():
    from app.main import api_docs_urls

    assert api_docs_urls("production") == {"docs_url": None, "redoc_url": None, "openapi_url": None}
    assert api_docs_urls("development") == {
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "openapi_url": "/openapi.json",
    }


def test_the_csp_docs_exemption_only_exists_where_the_docs_do():
    from fastapi import FastAPI

    from app.main import api_docs_urls, csp_exempt_paths

    # In production /docs is just a client route serving the SPA, which keeps its CSP.
    prod = api_docs_urls("production")
    off = FastAPI(docs_url=prod["docs_url"], redoc_url=prod["redoc_url"], openapi_url=prod["openapi_url"])
    assert csp_exempt_paths(off) == frozenset()
    assert csp_exempt_paths(FastAPI()) == {"/docs", "/docs/oauth2-redirect", "/redoc"}


def test_an_unknown_environment_fails_at_boot():
    with pytest.raises(ValidationError):
        _settings(environment="prod")


def test_mongodb_credentials_never_print():
    s = _settings(mongodb_url="mongodb://user:hunter2-secret@db:27017")
    assert "hunter2-secret" not in repr(s)


def test_the_real_app_serves_no_docs_or_schema_in_production(tmp_path):
    # Docs are decided at import from ENVIRONMENT, so boot the real app in a fresh
    # interpreter with production settings.
    import os
    import subprocess
    import sys
    from pathlib import Path

    # pytest.ini's filterwarnings doesn't reach a subprocess, so the probe sets its own
    # (before TestClient is imported, which is where the httpx fallback warns).
    probe = (
        "import warnings\n"
        "from starlette.exceptions import StarletteDeprecationWarning\n"
        "warnings.simplefilter('error', StarletteDeprecationWarning)\n"
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n"
        "assert app.openapi_url is None and app.docs_url is None and app.redoc_url is None\n"
        "c = TestClient(app)\n"
        "for p in ('/openapi.json', '/docs', '/redoc'):\n"
        "    r = c.get(p)\n"
        "    assert 'swagger' not in r.text.lower() and '\"openapi\"' not in r.text, p\n"
        "print('ok')\n"
    )
    env = {
        **os.environ,
        "ENVIRONMENT": "production",
        "JWT_SECRET_KEY": "x" * 40,
    }
    server_dir = Path(__file__).resolve().parents[1]
    (tmp_path / "dist").mkdir()  # production mounts the built client from ./dist
    (tmp_path / "dist" / "index.html").write_text('<div id="root"></div>')
    out = subprocess.run(  # noqa: S603 (a fixed probe run with this interpreter)
        [sys.executable, "-c", probe], cwd=tmp_path, env={**env, "PYTHONPATH": str(server_dir)},
        capture_output=True, text=True, timeout=120,
    )
    assert out.returncode == 0 and out.stdout.strip() == "ok", out.stderr[-400:]
