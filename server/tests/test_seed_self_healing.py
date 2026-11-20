"""`ensure_demo_seed` builds the whole demo on a fresh database and, on a seeded one,
repairs whatever is missing (records, stored files, the vector collection, the examples)
without a paid call. Runs against the test Mongo with a fake vector store, a temporary
`LocalStorage`, and a fixture loader patched to deterministic vectors."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
import pytest_asyncio

from app import database as database_mod
from app import main as main_mod
from app.config import settings
from app.routes import examples as examples_mod
from app.services import generations_service
from app.services.storage_service import LocalStorage, build_document_key
from seed import seed_demo
from seed.seed_demo import (
    CORPUS,
    EXAMPLES_FIXTURE,
    SeedReport,
    chunk_key,
    corpus_chunks,
    ensure_demo_seed,
)
from tests.conftest import TEST_DB_NAME
from tests.fakes import FakeVectorStore

EXAMPLE_KEYS = {"text-post", "card", "post-pack", "document"}


@dataclass
class SeedEnv:
    db: object
    store: FakeVectorStore
    storage: LocalStorage
    root: Path
    fixture: dict[str, list[float]]

    async def run(self, **kwargs) -> SeedReport:
        return await ensure_demo_seed(self.db, store=self.store, storage=self.storage, **kwargs)

    def exists(self, key: str) -> bool:
        return Path(self.storage.local_path(key)).is_file()

    def read(self, key: str) -> bytes:
        return Path(self.storage.local_path(key)).read_bytes()

    def remove(self, key: str) -> None:
        Path(self.storage.local_path(key)).unlink()


def _all_chunk_vectors() -> dict[str, list[float]]:
    chunks = corpus_chunks("any", {filename: "any" for filename, _, _ in CORPUS})
    return {chunk_key(c["text"]): [0.25] * settings.embedding_dim for c in chunks}


@pytest_asyncio.fixture
async def seed_env(test_db, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    fixture = _all_chunk_vectors()
    monkeypatch.setattr(seed_demo, "load_embeddings_fixture", lambda *a, **k: dict(fixture))
    return SeedEnv(test_db, FakeVectorStore(), LocalStorage(), tmp_path, fixture)


async def _workspace(db) -> dict:
    user = await db.users.find_one({"is_demo": True})
    return await db.workspaces.find_one({"owner_id": user["_id"], "slug": "verdure-materials"})


async def _examples(db) -> dict[str, dict]:
    return {d["example_key"]: d async for d in db.generations.find({"is_example": True})}


async def test_a_fresh_database_is_seeded_completely(seed_env):
    report = await seed_env.run()
    assert report.ok, report.error
    assert report.created and report.repaired == []
    db = seed_env.db

    assert await db.users.count_documents({"is_demo": True}) == 1
    ws = await _workspace(db)
    assert ws is not None
    assets = [a async for a in db.assets.find({"workspace_id": ws["_id"]})]
    assert sorted(a["filename"] for a in assets) == sorted(f for f, _, _ in CORPUS)
    assert all(seed_env.exists(a["storage_key"]) for a in assets)
    assert all(a["ingestion_status"] == "ready" for a in assets)

    total = sum(a["chunk_count"] for a in assets)
    assert total == len(corpus_chunks("any", {f: "any" for f, _, _ in CORPUS}))
    assert await seed_env.store.count(ws["vector_namespace"]) == total
    assert ws["ready_chunk_count"] == total
    assert ws["asset_count"] == len(CORPUS)

    assert seed_env.exists(ws["brand_profile"]["logo"]["storage_key"])
    assert all(seed_env.exists(e["storage_key"]) for e in ws["brand_profile"]["exemplars"])
    assert all(seed_env.exists(i["storage_key"]) for i in ws["brand_profile"]["brand_images"])
    templates = [t async for t in db.templates.find({"workspace_id": ws["_id"]})]
    assert len(templates) == 2 and all(seed_env.exists(t["storage_key"]) for t in templates)

    examples = await _examples(db)
    assert set(examples) == EXAMPLE_KEYS
    doc = examples["document"]
    for fmt in ("pdf", "docx"):
        key = build_document_key(str(ws["_id"]), str(doc["_id"]), fmt)
        assert doc["output"]["formats"][fmt]["storage_key"] == key
        assert seed_env.exists(key)
    assert seed_env.read(doc["output"]["formats"]["pdf"]["storage_key"])[:4] == b"%PDF"


async def test_a_second_run_repairs_nothing(seed_env):
    first = await seed_env.run()
    assert first.ok, first.error
    second = await seed_env.run()
    assert second.ok, second.error
    assert second.created == []
    assert second.repaired == []
    assert await seed_env.db.generations.count_documents({"is_example": True}) == 4


async def test_seed_repairs_missing_files_collection_and_examples_without_paid_calls(
    seed_env, monkeypatch
):
    assert (await seed_env.run()).ok
    db = seed_env.db
    ws = await _workspace(db)
    namespace = ws["vector_namespace"]
    corpus = await db.assets.find_one({"workspace_id": ws["_id"], "filename": "past-posts.md"})
    logo_key = ws["brand_profile"]["logo"]["storage_key"]
    examples = await _examples(db)
    pdf_key = examples["document"]["output"]["formats"]["pdf"]["storage_key"]

    seed_env.remove(corpus["storage_key"])
    seed_env.remove(logo_key)
    seed_env.remove(pdf_key)
    await seed_env.store.delete_workspace(namespace)
    await db.generations.delete_one({"_id": examples["card"]["_id"]})

    def no_paid_calls():
        raise AssertionError("the seed must not embed without embed_missing")

    monkeypatch.setattr("app.rag.embeddings.get_embedder", no_paid_calls)
    report = await seed_env.run()

    assert report.ok, report.error
    assert report.created == []
    for item in (
        "file past-posts.md",
        "logo file",
        "example file document.pdf",
        "vector collection",
        "example card",
    ):
        assert item in report.repaired, (item, report.repaired)
    assert seed_env.exists(corpus["storage_key"])
    assert seed_env.exists(logo_key)
    assert seed_env.exists(pdf_key)
    assert await seed_env.store.count(namespace) == ws["ready_chunk_count"]
    assert set(await _examples(db)) == EXAMPLE_KEYS
    assert await db.ai_spend_calls.count_documents({}) == 0


async def test_a_partly_populated_collection_is_rebuilt(seed_env):
    assert (await seed_env.run()).ok
    ws = await _workspace(seed_env.db)
    namespace = ws["vector_namespace"]
    asset = await seed_env.db.assets.find_one({"workspace_id": ws["_id"], "filename": "personas.md"})
    await seed_env.store.delete_asset(namespace, str(asset["_id"]))

    report = await seed_env.run()
    assert report.repaired == ["vector collection"]
    assert await seed_env.store.count(namespace) == ws["ready_chunk_count"]


async def test_an_out_of_date_fixture_is_an_error_without_embed_missing(
    seed_env, monkeypatch, fake_embedder
):
    stale = dict(seed_env.fixture)
    missing_key = next(iter(stale))
    stale.pop(missing_key)
    monkeypatch.setattr(seed_demo, "load_embeddings_fixture", lambda *a, **k: dict(stale))

    report = await seed_env.run()
    assert not report.ok
    assert "out of date" in (report.error or "")
    assert fake_embedder.calls == []
    assert await seed_env.db.ai_spend_calls.count_documents({}) == 0

    # --embed-missing embeds only the chunk the fixture lacks, through the ledger.
    repaired = await seed_env.run(embed_missing=True)
    assert repaired.ok, repaired.error
    assert "vector collection" in repaired.repaired
    assert len(fake_embedder.calls) == 1
    assert [chunk_key(t) for t in fake_embedder.calls[0]] == [missing_key]
    calls = [c async for c in seed_env.db.ai_spend_calls.find({})]
    assert len(calls) == 1 and calls[0]["provider"] == "openai" and calls[0]["status"] == "settled"
    ws = await _workspace(seed_env.db)
    assert await seed_env.store.count(ws["vector_namespace"]) == ws["ready_chunk_count"]


async def test_examples_are_marked_read_only_and_resolve_their_retrieval(seed_env):
    assert (await seed_env.run()).ok
    db = seed_env.db
    ws = await _workspace(db)
    demo = await db.users.find_one({"is_demo": True})
    assets = {a["filename"]: a async for a in db.assets.find({"workspace_id": ws["_id"]})}
    chunk_text = {
        (c["metadata"]["filename"], c["metadata"]["chunk_index"]): c["text"]
        for c in corpus_chunks("any", {f: "any" for f, _, _ in CORPUS})
    }
    examples = await _examples(db)

    for key, doc in examples.items():
        assert doc["is_example"] is True
        assert doc["session_id"] is None
        assert "expires_at" not in doc
        assert doc["owner_id"] == demo["_id"]
        assert doc["workspace_id"] == ws["_id"]
        assert doc["model"] == settings.ai_model
        assert doc["status"] == "complete"
        assert doc["brief"]
        meta = doc["retrieval_meta"]
        assert meta, key
        for item in meta:
            asset = assets[item["filename"]]
            assert item["asset_id"] == str(asset["_id"])
            assert item["asset_kind"] == asset["asset_kind"]
            assert item["chunk_id"] == f"{asset['_id']}:{item['chunk_index']}"
            assert item["preview"] == chunk_text[(item["filename"], item["chunk_index"])][:240]
        assert doc["retrieved_chunk_ids"] == [m["chunk_id"] for m in meta]

        response = generations_service.to_response(doc)
        assert response.is_example is True
        patched = await generations_service.update_generation_output(
            db, ws["_id"], str(doc["_id"]), {"accent_hex": "#1C3A2E"}, session_id=None
        )
        assert patched is None
        assert not await generations_service.delete_generation(
            db, ws["_id"], str(doc["_id"]), session_id=None
        )

    text = examples["text-post"]
    assert text["type"] == "text"
    assert text["output"]["hashtags"] and text["output"]["char_count"] == len(text["output"]["post_text"])

    card = examples["card"]["output"]
    assert examples["card"]["type"] == "card"
    assert card["template_id"] == "statement"
    assert card["accent_hex"] == "#C98A3D"
    assert card["image"] is None
    assert card["fields"]["headline"]

    pack = examples["post-pack"]
    assert pack["type"] == "post_pack"
    assert pack["output"]["post_text"] and pack["output"]["hashtags"]
    assert pack["output"]["card"]["template_id"] == "quote"
    assert pack["output"]["card"]["image"] is None

    document = examples["document"]
    assert document["type"] == "document"
    model = document["output"]["document"]
    assert model["archetype"] == "one-pager"
    assert len(model["sections"]) == 3
    assert all(s["bullets"] for s in model["sections"])


async def _use_app_indexes(seed_env, monkeypatch) -> None:
    """Create the app's real indexes on the test database (what the lifespan does)."""
    monkeypatch.setattr(database_mod.db, "client", seed_env.db.client)
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    await database_mod.ensure_indexes()


async def _example_keys(db, workspace_id) -> set[str]:
    query = {"workspace_id": workspace_id, "is_example": True}
    return {d["example_key"] async for d in db.generations.find(query)}


async def test_a_recreated_workspace_gets_its_own_examples(seed_env, monkeypatch):
    await _use_app_indexes(seed_env, monkeypatch)
    db = seed_env.db
    assert (await seed_env.run()).ok
    old = await _workspace(db)
    # The workspace is recreated; the old workspace's examples are still there.
    await db.workspaces.delete_one({"_id": old["_id"]})

    report = await seed_env.run()
    assert report.ok, report.error
    new = await _workspace(db)
    assert new["_id"] != old["_id"]
    assert await _example_keys(db, new["_id"]) == EXAMPLE_KEYS
    assert await _example_keys(db, old["_id"]) == EXAMPLE_KEYS
    assert {f"example {k}" for k in EXAMPLE_KEYS} <= set(report.created)

    page = await examples_mod._load(db)
    assert len(page.items) == 4
    assert {item.workspace_id for item in page.items} == {str(new["_id"])}


async def test_an_example_that_cannot_be_saved_is_an_error_and_leaves_no_files(seed_env):
    db = seed_env.db
    assert (await seed_env.run()).ok
    old = await _workspace(db)
    # Only the old document example remains, and a stale global index on example_key
    # makes the new workspace's document example collide with it.
    await db.generations.delete_many({"workspace_id": old["_id"], "example_key": {"$ne": "document"}})
    await db.workspaces.delete_one({"_id": old["_id"]})
    await db.generations.create_index(
        "example_key",
        name="stale_example_key",
        unique=True,
        partialFilterExpression={"example_key": {"$exists": True}},
    )
    try:
        report = await seed_env.run()
    finally:
        await db.generations.drop_index("stale_example_key")

    assert not report.ok
    assert "document" in (report.error or "")
    new = await _workspace(db)
    assert await _example_keys(db, new["_id"]) == {"text-post", "card", "post-pack"}
    documents = seed_env.root / str(new["_id"]) / "documents"
    assert [p for p in documents.rglob("*") if p.is_file()] == []


def test_the_examples_fixture_names_the_four_examples():
    import json

    data = json.loads(EXAMPLES_FIXTURE.read_text(encoding="utf-8"))
    assert [e["example_key"] for e in data["examples"]] == [
        "text-post",
        "card",
        "post-pack",
        "document",
    ]


# --- startup ---------------------------------------------------------------


@pytest.fixture
def startup_env(monkeypatch):
    # The lifespan connects the global client; put the old one back afterward.
    monkeypatch.setattr(database_mod.db, "client", None)
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    monkeypatch.setattr(settings, "seed_on_startup", True)


async def test_startup_runs_the_seed_and_keeps_its_report(test_db, startup_env, monkeypatch):
    calls: list[bool] = []

    async def fake_seed(db, *, store, storage, embed_missing=False):
        calls.append(embed_missing)
        return SeedReport(created=["workspace"], repaired=[], error=None)

    monkeypatch.setattr(main_mod, "ensure_demo_seed", fake_seed)
    async with main_mod.lifespan(main_mod.app):
        assert main_mod.app.state.seed_report.created == ["workspace"]
    assert calls == [False]


async def test_a_failed_startup_seed_is_recorded_and_the_app_still_starts(
    test_db, startup_env, monkeypatch
):
    async def broken_seed(db, *, store, storage, embed_missing=False):
        raise RuntimeError("disk full")

    monkeypatch.setattr(main_mod, "ensure_demo_seed", broken_seed)
    async with main_mod.lifespan(main_mod.app):
        report = main_mod.app.state.seed_report
        assert not report.ok
        assert report.error


async def test_startup_skips_the_seed_unless_asked(test_db, startup_env, monkeypatch):
    monkeypatch.setattr(settings, "seed_on_startup", False)

    async def must_not_run(*a, **k):
        raise AssertionError("seed ran with SEED_ON_STARTUP off")

    monkeypatch.setattr(main_mod, "ensure_demo_seed", must_not_run)
    async with main_mod.lifespan(main_mod.app):
        assert main_mod.app.state.seed_report is None
