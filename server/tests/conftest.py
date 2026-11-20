"""Shared fixtures. Unit tests use the in-memory fakes (no network); the
integration fixtures connect to the local docker Mongo and skip cleanly if it
isn't running."""
from __future__ import annotations

import tempfile
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.rag.loaders import Section
from app.rag.vector_store import get_vector_store
from app.services.ingestion_service import build_chunks
from app.utils.ratelimit import limiter
from tests.fakes import FakeEmbedder, FakeVectorStore

# The suite reuses one process (and one in-memory limiter), so cumulative requests
# to an endpoint would otherwise trip the SEC-02 limits. Disable rate limiting for
# tests; the limit behavior is covered explicitly in test_rate_limit.py.
limiter.enabled = False

# Chroma runs in-process on a directory, and only one process may open it. Point the
# suite at a throwaway directory before anything builds a store, so a test run never
# opens the dev data directory while `npm run dev` holds it.
settings.chroma_path = tempfile.mkdtemp(prefix="folio-test-chroma-")
get_vector_store.cache_clear()

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = REPO_ROOT / "docs" / "demo-corpus"

NS_A = "workspace-a"
NS_B = "workspace-b"

# corpus file -> (asset_id, asset_kind)
_CORPUS = {
    "voice-and-tone.md": ("voice-asset", "voice"),
    "content-pillars.md": ("pillars-asset", "pillars"),
    "past-posts.md": ("posts-asset", "posts"),
    "personas.md": ("personas-asset", "personas"),
    "competitors.md": ("competitors-asset", "competitors"),
}


def build_corpus_chunks(namespace: str) -> list[dict]:
    """Parse the real Verdure corpus into vector-store chunks for `namespace`."""
    chunks: list[dict] = []
    for filename, (asset_id, kind) in _CORPUS.items():
        text = (CORPUS_DIR / filename).read_text(encoding="utf-8")
        chunks.extend(
            build_chunks(
                workspace_namespace=namespace,
                asset_id=asset_id,
                asset_kind=kind,
                filename=filename,
                sections=[Section(text=text)],
            )
        )
    return chunks


TEST_DB_NAME = "brand_content_test"
TEST_COLLECTIONS = (
    "users",
    "workspaces",
    "assets",
    "generations",
    "templates",
    "usage",
    "ai_spend_days",
    "ai_spend_calls",
    "ai_spend_visitors",
)


@pytest_asyncio.fixture
async def test_db():
    """A clean Mongo database on the local docker instance. Skips the test if
    Mongo isn't reachable so the unit suite still runs anywhere."""
    from motor.motor_asyncio import AsyncIOMotorClient

    from app.config import settings

    client = AsyncIOMotorClient(
        settings.mongodb_url.get_secret_value(), serverSelectionTimeoutMS=1500
    )
    try:
        await client.admin.command("ping")
    except Exception:
        client.close()
        pytest.skip("MongoDB not reachable (start docker-compose) — skipping integration test")

    db = client[TEST_DB_NAME]
    for coll in TEST_COLLECTIONS:
        await db[coll].delete_many({})
    try:
        yield db
    finally:
        for coll in TEST_COLLECTIONS:
            await db[coll].delete_many({})
        client.close()


@pytest.fixture
def fake_store() -> FakeVectorStore:
    return FakeVectorStore()


@pytest_asyncio.fixture
async def ingested_store() -> FakeVectorStore:
    """A fake store with the full Verdure corpus ingested into NS_A."""
    store = FakeVectorStore()
    await store.upsert_chunks(NS_A, build_corpus_chunks(NS_A))
    return store


_ALLOWED_TRANSPORTS = (httpx.ASGITransport, httpx.MockTransport)


def _guarded(original, transport_of):
    def send(self, request, *args, **kwargs):
        if not isinstance(transport_of(self), _ALLOWED_TRANSPORTS):
            raise AssertionError(f"real network call in a test: {request.url.host}")
        return original(self, request, *args, **kwargs)

    return send


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """The suite's guard against paid calls: an httpx request fails unless the
    client's transport is the in-process ASGI app or a mock. Every Anthropic,
    OpenAI, and Unsplash call goes through httpx; Mongo (Motor) does not."""
    def transport_of(client):
        return client._transport

    monkeypatch.setattr(
        httpx.AsyncClient, "send", _guarded(httpx.AsyncClient.send, transport_of)
    )
    monkeypatch.setattr(httpx.Client, "send", _guarded(httpx.Client.send, transport_of))


@pytest.fixture(autouse=True)
def fake_embedder(monkeypatch) -> FakeEmbedder:
    """Every embedding in the suite goes to a deterministic fake, never OpenAI."""
    embedder = FakeEmbedder()
    monkeypatch.setattr("app.rag.embeddings.get_embedder", lambda: embedder)
    return embedder
