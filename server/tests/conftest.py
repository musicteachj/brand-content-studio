"""Shared fixtures. Unit tests use the in-memory fakes (no network); the
integration fixtures connect to the local docker Mongo and skip cleanly if it
isn't running."""
from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from app.rag.loaders import Section
from app.services.ingestion_service import build_chunks
from app.utils.ratelimit import limiter
from tests.fakes import FakeVectorStore

# The suite reuses one process (and one in-memory limiter), so cumulative requests
# to an endpoint would otherwise trip the SEC-02 limits. Disable rate limiting for
# tests; the limit behavior is covered explicitly in test_rate_limit.py.
limiter.enabled = False

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
    for coll in ("users", "workspaces", "assets", "generations", "templates", "usage"):
        await db[coll].delete_many({})
    try:
        yield db
    finally:
        for coll in ("users", "workspaces", "assets", "generations", "templates", "usage"):
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
