"""Application settings (pydantic-settings). Loads from server/.env."""
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The shipped placeholder. Signing with it in production would let anyone forge a
# token for any user_id, so a production boot that still has it must fail closed.
DEFAULT_JWT_SECRET = "CHANGE-THIS-IN-PRODUCTION"  # noqa: S105 — placeholder; rejected in prod below
MIN_JWT_SECRET_LEN = 32


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
    # Aggregate cap on the shared demo account's paid AI actions per UTC day: every
    # paid model route (generations, brand extract, template AI fill, fill from a
    # document) consumes one. Per-IP rate limits don't bound total demo spend
    # across many visitors. The name predates the non-saving routes being counted.
    demo_daily_generation_limit: int = 50

    # Content-Security-Policy (known-gaps plan, step 2): "enforce" sends it,
    # "report-only" sends it as Content-Security-Policy-Report-Only (to ease off
    # after a regression without a code change), "off" sends neither.
    csp_mode: Literal["enforce", "report-only", "off"] = "enforce"

    # Per-IP rate limits (slowapi syntax) — env-tunable (SEC-02).
    rate_limit_auth: str = "10/minute"
    rate_limit_generate: str = "30/minute"

    # AI — generation (Anthropic)
    anthropic_api_key: SecretStr = SecretStr("")
    ai_model: str = "claude-sonnet-4-6"

    # AI — embeddings (OpenAI)
    openai_api_key: SecretStr = SecretStr("")
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    # Vector store: "chroma" (dev) | "qdrant" (prod)
    vector_store_backend: str = "chroma"
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "brand-content-studio"

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


settings = Settings()
