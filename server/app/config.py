"""Application settings (pydantic-settings). Loads from server/.env."""
import ipaddress
from decimal import Decimal
from pathlib import Path
from typing import Final, Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.services.ai_pricing import is_priced

# The shipped placeholder. Signing with it in production would let anyone forge a
# token for any user_id, so a production boot that still has it must fail closed.
DEFAULT_JWT_SECRET = "CHANGE-THIS-IN-PRODUCTION"  # noqa: S105 — placeholder; rejected in prod below
MIN_JWT_SECRET_LEN = 32

# Cloudflare Turnstile's documented test values (developers.cloudflare.com/turnstile/
# troubleshooting/testing/, re-checked 2026-11-20). The site key always passes; the
# secrets pass, always fail, and answer "token already spent". They are answered
# locally (app/services/turnstile.py), never by siteverify, and production refuses
# them unless APP_ORIGIN is a loopback origin.
TURNSTILE_TEST_SITE_KEY: Final = "1x00000000000000000000AA"
TURNSTILE_PASS_SECRET: Final = "1x0000000000000000000000000000000AA"  # noqa: S105 (public test value)
TURNSTILE_FAIL_SECRET: Final = "2x0000000000000000000000000000000AA"  # noqa: S105 (public test value)
TURNSTILE_SPENT_SECRET: Final = "3x0000000000000000000000000000000AA"  # noqa: S105 (public test value)
TURNSTILE_TEST_SECRETS: Final = frozenset(
    {TURNSTILE_PASS_SECRET, TURNSTILE_FAIL_SECRET, TURNSTILE_SPENT_SECRET}
)
_LOOPBACK_HOSTS: Final = frozenset({"localhost", "127.0.0.1"})


class Settings(BaseSettings):
    # Secrets are SecretStr, so printing the settings (a traceback, a log line,
    # a validation error) shows "**********"; read one with .get_secret_value()
    # only where it's handed to its provider. Note SecretStr("") is truthy: to ask
    # "is this key set?", test .get_secret_value(), never the field itself.

    # App
    # A fixed set, so a typo ("prod") fails at boot instead of quietly skipping the
    # production-only checks (the JWT secret, docs off, HSTS).
    environment: Literal["development", "production"] = "development"
    cors_origins: list[str] = ["http://localhost:5173"]
    # Proxies whose X-Forwarded-For uvicorn may trust: comma-separated IPs or CIDRs.
    # uvicorn reads FORWARDED_ALLOW_IPS from the environment itself (the Dockerfile
    # never passes it on the command line); this field only lets the production
    # check below see and vet the same value.
    forwarded_allow_ips: str = "127.0.0.1"
    # Where visitors reach the app. Turnstile tokens must have been issued for its host,
    # and production requires https here (unless it is a loopback origin).
    app_origin: str = "http://localhost:5173"

    # MongoDB
    mongodb_url: SecretStr = SecretStr("mongodb://localhost:27017")  # may carry credentials
    database_name: str = "brand_content"

    # JWT
    jwt_secret_key: SecretStr = SecretStr(DEFAULT_JWT_SECRET)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Seeded demo user ("Explore as demo")
    demo_email: str = "demo@folio.studio"
    demo_password: str = "demo-folio-2026"  # noqa: S105 — public demo credential, not a secret
    demo_full_name: str = "Demo User"

    # Visitor demo starts: Cloudflare Turnstile keys (both blank outside production means
    # Cloudflare's always-pass test pair) and per-IP start limits.
    turnstile_site_key: str = ""
    turnstile_secret_key: SecretStr = SecretStr("")
    demo_starts_per_hour: int = 15
    demo_starts_per_day: int = 50

    # Content-Security-Policy (known-gaps plan, step 2): "enforce" sends it,
    # "report-only" sends it as Content-Security-Policy-Report-Only (to ease off
    # after a regression without a code change), "off" sends neither.
    csp_mode: Literal["enforce", "report-only", "off"] = "enforce"

    # Per-IP rate limits (slowapi syntax) — env-tunable (SEC-02).
    rate_limit_auth: str = "10/minute"
    rate_limit_generate: str = "30/minute"

    # AI — generation (Anthropic)
    anthropic_api_key: SecretStr = SecretStr("")
    ai_model: str = "claude-sonnet-5-5"
    # How much the model thinks before it writes (DECISIONS #40). "low" is the
    # recommended start for content generation and extraction; raise it with an
    # env change if quality looks thin.
    ai_effort: Literal["low", "medium", "high"] = "low"

    # AI timeouts, in seconds. The SDKs never retry (a retry is a second billed call).
    # Whole-request timeout for a non-streamed call, the longest silence allowed
    # between streamed chunks, and the deadline for a whole streamed call.
    ai_request_timeout_s: float = 60.0
    ai_stream_read_timeout_s: float = 30.0
    ai_stream_deadline_s: float = 90.0

    # The AI dollar ledger (ai_ledger.py). A budget of 0 means live AI is off.
    ai_monthly_budget_usd: Decimal = Decimal("10")
    ai_pacing_multiplier: Decimal = Decimal("3")
    ai_daily_floor_usd: Decimal = Decimal("0.50")
    ai_visitor_budget_usd: Decimal = Decimal("0.15")

    # AI — embeddings (OpenAI)
    openai_api_key: SecretStr = SecretStr("")
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    embedding_timeout_s: float = 10.0

    # Vector store: Chroma runs in-process on local disk (no server). One process only.
    vector_store_backend: str = "chroma"
    chroma_path: str = "./chroma"

    # Storage: "local" (dev) | "s3" (prod)
    storage_backend: str = "local"
    storage_local_dir: str = "./storage"
    s3_bucket: str = ""

    # Documents (Phase 2) — optional brand-font TTFs for exact PDF font embedding.
    # Drop `<font-slug>.ttf` files here (e.g. dm-serif-display.ttf) to embed real
    # brand fonts in generated PDFs; missing fonts fall back to a serif/sans base
    # font. No runtime network fetch — keeps the request path SSRF-free.
    brand_fonts_dir: str = str(Path(__file__).resolve().parent / "assets" / "fonts")

    # Images
    unsplash_access_key: SecretStr = SecretStr("")

    # hide_input_in_errors: a validation error at boot would otherwise quote the raw
    # input (every env setting, API keys included) into the logs as input_value.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    @model_validator(mode="after")
    def _reject_default_secrets_in_production(self) -> "Settings":
        """Fail closed rather than boot a production app with a public signing key.
        The Dockerfile hard-sets ENVIRONMENT=production, so a container launched
        without JWT_SECRET_KEY would otherwise start happily and sign forgeable
        tokens."""
        if self.environment != "production":
            return self
        secret = self.jwt_secret_key.get_secret_value()
        if secret == DEFAULT_JWT_SECRET:
            raise ValueError(
                "JWT_SECRET_KEY is still the shipped default. Set it to a random "
                f"string of at least {MIN_JWT_SECRET_LEN} characters."
            )
        if len(secret) < MIN_JWT_SECRET_LEN:
            raise ValueError(
                f"JWT_SECRET_KEY must be at least {MIN_JWT_SECRET_LEN} characters "
                "in production."
            )
        return self


def turnstile_keys(s: Settings) -> tuple[str, str]:
    """The (site key, secret) the app uses. Both blank outside production gives
    Cloudflare's always-pass test pair, so local development needs no Cloudflare account."""
    site = s.turnstile_site_key.strip()
    secret = s.turnstile_secret_key.get_secret_value().strip()
    if not site and not secret and s.environment != "production":
        return TURNSTILE_TEST_SITE_KEY, TURNSTILE_PASS_SECRET
    return site, secret


def _is_loopback_origin(origin: str) -> bool:
    parts = urlsplit(origin)
    return parts.scheme == "http" and parts.hostname in _LOOPBACK_HOSTS


def validate_serving_settings(s: Settings) -> None:
    """Production-only checks on how the app is served, run once at the start of the
    lifespan. They live here and not in the import-time validator above so the hourly
    cleanup job can import the settings without the web app's serving config."""
    if s.environment != "production":
        return
    if "forwarded_allow_ips" not in s.model_fields_set:
        raise ValueError(
            "FORWARDED_ALLOW_IPS must be set in production, to the load balancer's "
            "CIDR (for example the VPC range), so the rate limiter sees real client IPs."
        )
    entries = [e.strip() for e in s.forwarded_allow_ips.split(",") if e.strip()]
    if not entries:
        raise ValueError("FORWARDED_ALLOW_IPS is empty; list the trusted proxy IPs or CIDRs.")
    for entry in entries:
        if entry == "*":
            raise ValueError(
                "FORWARDED_ALLOW_IPS must not be '*': it would trust a forged X-Forwarded-For."
            )
        try:
            network = ipaddress.ip_network(entry, strict=False)
        except ValueError:
            raise ValueError(
                f"FORWARDED_ALLOW_IPS entry {entry!r} is not an IP address or CIDR."
            ) from None
        if network.prefixlen == 0:
            raise ValueError(
                f"FORWARDED_ALLOW_IPS entry {entry!r} trusts every address; use the "
                "load balancer's CIDR."
            )

    loopback = _is_loopback_origin(s.app_origin)
    parts = urlsplit(s.app_origin)
    if not loopback and (parts.scheme != "https" or not parts.hostname):
        raise ValueError(
            "APP_ORIGIN must be the https origin visitors use (for example "
            "https://folio.example.com); plain http is allowed only for a loopback origin."
        )
    site, secret = turnstile_keys(s)
    if not site or not secret:
        raise ValueError(
            "TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY must both be set in production."
        )
    if (site == TURNSTILE_TEST_SITE_KEY or secret in TURNSTILE_TEST_SECRETS) and not loopback:
        raise ValueError(
            "The Turnstile test keys are allowed in production only when APP_ORIGIN is a "
            "loopback origin (http://localhost or http://127.0.0.1); set the real keys."
        )
    if not is_priced(s.ai_model):
        raise ValueError(
            f"AI_MODEL {s.ai_model!r} has no price in ai_pricing, so the AI ledger could "
            "not count its spend."
        )


settings = Settings()
