from datetime import UTC, datetime, timedelta

from app.jobs import cleanup
from app.services.ai_ledger import LineRequest, reserve, settle

NOV19 = datetime(2026, 11, 19, 15, tzinfo=UTC)


def _req(m):
    return LineRequest("anthropic", "claude-sonnet-5-5", "test", m)


async def test_run_cleanup_sweeps_a_stale_reservation_and_prunes_an_old_settled_call(test_db):
    old = NOV19 - timedelta(days=40)
    (done,) = await reserve(test_db, [_req(1_000)], visitor_id=None, now=old)
    await settle(test_db, done, actual_micros=0, outcome="ok", now=old)
    await reserve(test_db, [_req(1_000)], visitor_id=None, now=NOV19 - timedelta(minutes=30))
    assert await cleanup.run_cleanup(test_db, now=NOV19) == {"swept": 1, "pruned": 1}


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
        return {"swept": 2, "pruned": 3}

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
    assert "cleanup: swept=2 pruned=3" in caplog.text
