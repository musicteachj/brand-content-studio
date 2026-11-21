import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from bson import ObjectId

from app.config import settings
from app.jobs import cleanup
from app.services import storage_service
from app.services.ai_ledger import LineRequest, reserve, settle
from app.services.session_service import SESSION_TTL, create_session
from app.services.storage_service import build_document_key

NOV19 = datetime(2026, 11, 19, 15, tzinfo=UTC)
WS_OID = ObjectId()
DEMO_OID = ObjectId()
SERVER_DIR = Path(__file__).resolve().parents[1]


def _req(m):
    return LineRequest("anthropic", "claude-sonnet-5-5", "test", m)


def _counts(**kw: int) -> dict[str, int]:
    return {
        "swept": 0,
        "pruned": 0,
        "expired_generations": 0,
        "orphaned_documents": 0,
        "expired_sessions": 0,
        **kw,
    }


@pytest.fixture(autouse=True)
def _temporary_storage(monkeypatch, tmp_path):
    # Every run_cleanup here scans file storage for orphaned documents: point it at a
    # temporary directory, never the real ./storage.
    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    storage_service.get_storage.cache_clear()
    yield
    storage_service.get_storage.cache_clear()


async def test_run_cleanup_sweeps_a_stale_reservation_and_prunes_an_old_settled_call(test_db):
    old = NOV19 - timedelta(days=40)
    (done,) = await reserve(test_db, [_req(1_000)], visitor_id=None, now=old)
    await settle(test_db, done, actual_micros=0, outcome="ok", now=old)
    await reserve(test_db, [_req(1_000)], visitor_id=None, now=NOV19 - timedelta(minutes=30))
    assert await cleanup.run_cleanup(test_db, now=NOV19) == _counts(swept=1, pruned=1)


def test_main_exits_1_when_cleanup_fails(monkeypatch):
    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("no mongo")

    monkeypatch.setattr(cleanup, "AsyncIOMotorClient", Boom)
    try:
        cleanup.main()
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("main() should exit 1")


def test_main_logs_the_counts(monkeypatch, caplog):
    async def fake_run(db, *, now=None):
        return {
            "swept": 2,
            "pruned": 3,
            "expired_generations": 4,
            "orphaned_documents": 6,
            "expired_sessions": 5,
        }

    class FakeClient:
        def __init__(self, *a, **k):
            self.kwargs = k

        def __getitem__(self, name):
            return object()

        def close(self):
            pass

    monkeypatch.setattr(cleanup, "AsyncIOMotorClient", FakeClient)
    monkeypatch.setattr(cleanup, "run_cleanup", fake_run)
    caplog.set_level("INFO")
    cleanup.main()
    assert "cleanup: swept=2 pruned=3 expired_generations=4 orphaned_documents=6 expired_sessions=5" in caplog.text


# --- expired visitor work and sessions ---------------------------------------


class _RecordingStorage:
    """The real local storage, noting for each prefix delete whether the generation's
    record was still there when its files went."""

    def __init__(self, db, inner) -> None:
        self.db = db
        self.inner = inner
        self.record_present_at_delete: dict[str, bool] = {}
        self.strict_calls: list[bool] = []

    async def delete_prefix(self, prefix: str, *, strict: bool = False) -> None:
        gid = prefix.rsplit("/", 1)[-1]
        found = await self.db.generations.find_one({"_id": ObjectId(gid)})
        self.record_present_at_delete[gid] = found is not None
        self.strict_calls.append(strict)
        await self.inner.delete_prefix(prefix, strict=strict)

    async def document_prefixes_before(self, older_than):
        return await self.inner.document_prefixes_before(older_than)


class _FailingStorage:
    async def delete_prefix(self, prefix: str, *, strict: bool = False) -> None:
        raise OSError("disk unavailable")

    async def document_prefixes_before(self, older_than):
        return []


@pytest.fixture
def tmp_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    storage_service.get_storage.cache_clear()
    yield storage_service.get_storage()
    storage_service.get_storage.cache_clear()


@pytest.fixture
def failing_storage(monkeypatch):
    storage = _FailingStorage()
    monkeypatch.setattr(cleanup, "get_storage", lambda: storage)
    return storage


async def _session(db, *, expired: bool) -> dict:
    created = NOV19 - SESSION_TTL - timedelta(minutes=5) if expired else NOV19 - timedelta(hours=1)
    return await create_session(db, user_id=DEMO_OID, now=created)


async def _generation(db, *, type_: str, session: dict | None = None, is_example: bool = False,
                      storage=None) -> str:
    oid = ObjectId()
    doc: dict = {
        "_id": oid, "workspace_id": WS_OID, "owner_id": DEMO_OID, "type": type_, "brief": "b",
        "status": "complete", "output": {}, "retrieved_chunk_ids": [], "retrieval_meta": [],
        "model": "m", "embedding_query_model": "e", "created_at": NOV19, "updated_at": NOV19,
    }
    if session is not None:
        doc["session_id"] = session["_id"]
        doc["expires_at"] = session["expires_at"]
    if is_example:
        doc["is_example"] = True
    if storage is not None:
        for fmt in ("docx", "pdf"):
            await storage.save(build_document_key(str(WS_OID), str(oid), fmt), b"file")
    await db.generations.insert_one(doc)
    return str(oid)


def _has_files(storage, gid: str) -> bool:
    return os.path.isdir(os.path.dirname(storage.local_path(build_document_key(str(WS_OID), gid, "pdf"))))


async def test_cleanup_removes_expired_visitor_work_files_first(test_db, tmp_storage, monkeypatch):
    recording = _RecordingStorage(test_db, tmp_storage)
    monkeypatch.setattr(cleanup, "get_storage", lambda: recording)
    expired = await _session(test_db, expired=True)
    live = await _session(test_db, expired=False)
    old_doc = await _generation(test_db, type_="document", session=expired, storage=tmp_storage)
    old_text = await _generation(test_db, type_="text", session=expired)
    live_doc = await _generation(test_db, type_="document", session=live, storage=tmp_storage)
    example = await _generation(test_db, type_="document", is_example=True, storage=tmp_storage)
    owner_card = await _generation(test_db, type_="card")

    counts = await cleanup.run_cleanup(test_db, now=NOV19)

    assert counts == _counts(expired_generations=2, expired_sessions=1)
    assert recording.record_present_at_delete[old_doc] is True
    assert recording.strict_calls and all(recording.strict_calls)
    assert not _has_files(tmp_storage, old_doc)
    left = {str(d["_id"]) async for d in test_db.generations.find({})}
    assert left == {live_doc, example, owner_card}
    assert old_text not in left
    assert _has_files(tmp_storage, live_doc)
    assert _has_files(tmp_storage, example)
    assert await test_db.demo_sessions.find_one({"_id": live["_id"]}) is not None
    assert await test_db.demo_sessions.find_one({"_id": expired["_id"]}) is None

    # Nothing is left to do on the next run.
    assert await cleanup.run_cleanup(test_db, now=NOV19) == _counts()


async def test_a_failed_file_delete_keeps_the_records_for_the_next_run(test_db, failing_storage):
    expired = await _session(test_db, expired=True)
    old_doc = await _generation(test_db, type_="document", session=expired)
    old_text = await _generation(test_db, type_="text", session=expired)

    with pytest.raises(RuntimeError, match="2 expired generations"):
        await cleanup.run_cleanup(test_db, now=NOV19)

    left = {str(d["_id"]) async for d in test_db.generations.find({})}
    assert left == {old_doc, old_text}


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores directory permissions"
)
async def test_an_undeletable_folder_in_real_storage_keeps_the_record(test_db, tmp_storage):
    """The real LocalStorage, not a fake: a generation folder whose files can't be removed
    must fail the run and keep the record, not orphan the files behind a deleted record."""
    expired = await _session(test_db, expired=True)
    gid = await _generation(test_db, type_="document", session=expired, storage=tmp_storage)
    folder = os.path.dirname(tmp_storage.local_path(build_document_key(str(WS_OID), gid, "pdf")))
    os.chmod(folder, 0o500)  # read and enter only: its files can't be unlinked
    try:
        with pytest.raises(RuntimeError, match="1 expired generations"):
            await cleanup.run_cleanup(test_db, now=NOV19)
        assert await test_db.generations.find_one({"_id": ObjectId(gid)}) is not None
        assert _has_files(tmp_storage, gid)
        # Sessions still go this run; the kept record carries its own expiry.
        assert await test_db.demo_sessions.find_one({"_id": expired["_id"]}) is None
    finally:
        os.chmod(folder, 0o700)

    # Once the folder can be removed, the next run finishes the job.
    assert await cleanup.run_cleanup(test_db, now=NOV19) == _counts(expired_generations=1)
    assert await test_db.generations.find_one({"_id": ObjectId(gid)}) is None
    assert not _has_files(tmp_storage, gid)


def _folder_exists(path: str) -> bool:
    return os.path.isdir(path)


async def _document_folder(storage, gid: str, *, age: timedelta) -> str:
    """A document folder under WS_OID, last changed `age` before NOV19."""
    await storage.save(build_document_key(str(WS_OID), gid, "pdf"), b"file")
    folder = os.path.dirname(storage.local_path(build_document_key(str(WS_OID), gid, "pdf")))
    stamp = (NOV19 - age).timestamp()
    os.utime(folder, (stamp, stamp))
    return folder


async def test_cleanup_removes_old_document_folders_that_no_record_points_at(test_db, tmp_storage):
    await test_db.workspaces.insert_one({"_id": WS_OID, "name": "Verdure"})
    orphan = str(ObjectId())
    in_flight = str(ObjectId())
    kept = await _generation(test_db, type_="document")  # the owner's: no expiry, files kept
    orphan_folder = await _document_folder(tmp_storage, orphan, age=timedelta(hours=25))
    in_flight_folder = await _document_folder(tmp_storage, in_flight, age=timedelta(minutes=1))
    kept_folder = await _document_folder(tmp_storage, kept, age=timedelta(days=30))
    odd_folder = await _document_folder(tmp_storage, "not-a-generation", age=timedelta(days=30))

    counts = await cleanup.run_cleanup(test_db, now=NOV19)

    assert counts == _counts(orphaned_documents=1)
    assert not _folder_exists(orphan_folder)
    assert _folder_exists(in_flight_folder)  # still being written, as far as anyone knows
    assert _folder_exists(kept_folder)
    assert _folder_exists(odd_folder)
    assert await cleanup.run_cleanup(test_db, now=NOV19) == _counts()


async def test_the_sweep_deletes_nothing_against_a_database_with_no_generations(
    test_db, tmp_storage
):
    # A cleanup task pointed at the wrong DATABASE_NAME or MONGODB_URL: every folder looks
    # like an orphan there, so the sweep must not run at all.
    await test_db.workspaces.insert_one({"_id": WS_OID, "name": "Verdure"})
    folder = await _document_folder(tmp_storage, str(ObjectId()), age=timedelta(days=30))

    assert await cleanup.run_cleanup(test_db, now=NOV19) == _counts()
    assert _folder_exists(folder)


async def test_the_sweep_leaves_folders_under_a_workspace_it_does_not_know(test_db, tmp_storage):
    # Generations exist, but the folder's workspace isn't in this database: leave it.
    await _generation(test_db, type_="text")
    folder = await _document_folder(tmp_storage, str(ObjectId()), age=timedelta(days=30))

    assert await cleanup.run_cleanup(test_db, now=NOV19) == _counts()
    assert _folder_exists(folder)


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores directory permissions"
)
async def test_an_undeletable_orphan_fails_the_run_after_the_rest(test_db, tmp_storage):
    await test_db.workspaces.insert_one({"_id": WS_OID, "name": "Verdure"})
    await _generation(test_db, type_="text")
    expired = await _session(test_db, expired=True)
    folder = await _document_folder(tmp_storage, str(ObjectId()), age=timedelta(days=2))
    os.chmod(folder, 0o500)
    try:
        with pytest.raises(RuntimeError, match="1 orphaned document folders"):
            await cleanup.run_cleanup(test_db, now=NOV19)
        assert _folder_exists(folder)
        assert await test_db.demo_sessions.find_one({"_id": expired["_id"]}) is None
    finally:
        os.chmod(folder, 0o700)


async def test_a_failed_orphan_scan_still_removes_expired_sessions(test_db, monkeypatch):
    class _ScanFails:
        async def delete_prefix(self, prefix, *, strict=False):
            pass

        async def document_prefixes_before(self, older_than):
            raise PermissionError("storage root unreadable")

    monkeypatch.setattr(cleanup, "get_storage", lambda: _ScanFails())
    await _generation(test_db, type_="text")  # past the empty-database guard, into the scan
    expired = await _session(test_db, expired=True)

    with pytest.raises(PermissionError):
        await cleanup.run_cleanup(test_db, now=NOV19)
    assert await test_db.demo_sessions.find_one({"_id": expired["_id"]}) is None


async def test_the_sweep_skips_prefixes_of_another_shape(test_db, monkeypatch):
    removed: list[str] = []
    gid = str(ObjectId())

    class _OddPrefixes:
        async def delete_prefix(self, prefix, *, strict=False):
            removed.append(prefix)

        async def document_prefixes_before(self, older_than):
            return [gid, f"{WS_OID}/documents", f"{WS_OID}/images/{gid}", f"{WS_OID}/documents/{gid}/x"]

    monkeypatch.setattr(cleanup, "get_storage", lambda: _OddPrefixes())
    await test_db.workspaces.insert_one({"_id": WS_OID, "name": "Verdure"})
    await _generation(test_db, type_="text")

    assert await cleanup.run_cleanup(test_db, now=NOV19) == _counts()
    assert removed == []


def test_the_scan_skips_a_folder_that_vanishes(tmp_storage, monkeypatch):
    import asyncio as _asyncio
    from pathlib import Path as _Path

    gid = str(ObjectId())
    _asyncio.run(tmp_storage.save(build_document_key(str(WS_OID), gid, "pdf"), b"file"))
    real_stat = _Path.stat

    def stat(self, *a, **k):
        if self.name == gid:
            raise FileNotFoundError(self)
        return real_stat(self, *a, **k)

    monkeypatch.setattr(_Path, "stat", stat)
    assert _asyncio.run(tmp_storage.document_prefixes_before(NOV19 + timedelta(days=9999))) == []


def test_main_exits_1_when_files_cannot_be_removed(monkeypatch):
    async def failing_run(db, *, now=None):
        raise RuntimeError("Couldn't remove the files for 1 expired generations")

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __getitem__(self, name):
            return object()

        def close(self):
            pass

    monkeypatch.setattr(cleanup, "AsyncIOMotorClient", FakeClient)
    monkeypatch.setattr(cleanup, "run_cleanup", failing_run)
    with pytest.raises(SystemExit) as exc:
        cleanup.main()
    assert exc.value.code == 1


async def test_cleanup_removes_expired_sessions_and_their_visitor_spend_but_not_day_totals(test_db):
    expired = await _session(test_db, expired=True)
    live = await _session(test_db, expired=False)
    for session in (expired, live):
        when = session["created_at"] + timedelta(minutes=1)
        (line,) = await reserve(test_db, [_req(1_000)], visitor_id=session["_id"], now=when)
        await settle(test_db, line, actual_micros=700, outcome="ok", now=when)
    days_before = await test_db.ai_spend_days.find({}).sort("_id", 1).to_list(None)
    assert days_before

    counts = await cleanup.run_cleanup(test_db, now=NOV19)

    assert counts["expired_sessions"] == 1
    assert await test_db.demo_sessions.find_one({"_id": expired["_id"]}) is None
    assert await test_db.ai_spend_visitors.find_one({"_id": expired["_id"]}) is None
    assert await test_db.demo_sessions.find_one({"_id": live["_id"]}) is not None
    assert (await test_db.ai_spend_visitors.find_one({"_id": live["_id"]}))["total_micros"] == 700
    assert await test_db.ai_spend_days.find({}).sort("_id", 1).to_list(None) == days_before


def test_the_cleanup_job_never_imports_chroma():
    code = "import sys, app.jobs.cleanup; assert 'chromadb' not in sys.modules, 'chromadb imported'"
    result = subprocess.run(  # noqa: S603 (fixed argv: this interpreter and a literal)
        [sys.executable, "-c", code], cwd=SERVER_DIR, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
