"""Shared slowapi limiter (SEC-02).

In-memory storage keyed by client IP — correct for the current single-instance
deploy; point the limiter at a Redis `storage_uri` when the app runs
multi-instance. Tests disable it via `limiter.enabled = False` (conftest).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

limiter = Limiter(key_func=get_remote_address)

# Per-IP limits (values in config so they're env-tunable). Login/demo-login:
# credential stuffing + demo-token farming. Generate + the other paid AI routes
# (brand-extract, template ai-fill/fill-from-document): Anthropic/OpenAI calls.
# Aggregate demo spend is additionally coupled to the per-account daily quota
# (enforce_demo_ai_quota).
AUTH_RATE_LIMIT = settings.rate_limit_auth
GENERATE_RATE_LIMIT = settings.rate_limit_generate
