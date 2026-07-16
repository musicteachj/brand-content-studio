"""Shared slowapi limiter (SEC-02).

In-memory storage keyed by client IP — correct for the current single-instance
deploy; point the limiter at a Redis `storage_uri` when the app runs
multi-instance. Tests disable it via `limiter.enabled = False` (conftest).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Per-IP limits. Login/demo-login: credential stuffing + demo-token farming.
# Generation: paid Anthropic/OpenAI calls. Aggregate demo spend is bounded
# separately by the per-account daily quota (enforce_demo_generation_quota).
AUTH_RATE_LIMIT = "10/minute"
GENERATE_RATE_LIMIT = "30/minute"
