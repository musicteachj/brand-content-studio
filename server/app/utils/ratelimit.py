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
# Aggregate spend is bounded separately by the AI dollar ledger (ai_ledger), which
# reserves every model call before it runs.
AUTH_RATE_LIMIT = settings.rate_limit_auth
GENERATE_RATE_LIMIT = settings.rate_limit_generate
# Unsplash search and download tracking: the access key's hourly quota is shared by
# every visitor, so one network can't spend it (search results are also cached).
RATE_LIMIT_UNSPLASH = settings.rate_limit_unsplash
