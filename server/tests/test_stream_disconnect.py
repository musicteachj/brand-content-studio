"""A visitor who leaves mid-stream must not leave a ledger line open until the sweeper
charges it. The real app is driven with a raw ASGI call to `/generate/text`, and the
client disconnects the way each ASGI spec version reports it:

- 2.3: `receive()` returns `http.disconnect` and Starlette cancels the response task.
- 2.4: `send()` raises `OSError` and Starlette raises `ClientDisconnect` without closing
  the body generator.

Three moments are covered: while the model is silent (the failing send is a heartbeat),
while it streams steadily (the failing send is a text frame), and before the body is
first read (the route's event generator never starts). Each time, by the time the app
call returns, the model's stream has been closed (before the route settled) and the
line is settled: at the full reservation once the call started (an unknown outcome is
billed), at 0 if it never did."""
import asyncio
import contextlib
import functools
import json
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from bson import ObjectId
from starlette.requests import ClientDisconnect

import app.routes.generate as generate_mod
from app.config import settings
from app.database import get_database
from app.main import app
from app.models.common import utcnow
from app.models.user import UserInDB
from app.services.ai_meter import MeteredLine
from app.services.ai_pricing import embedding_cost_micros
from app.services.ai_service import GenerationService
from app.utils.dependencies import get_current_user
from app.utils.sse import HEARTBEAT, sse_response
from tests.conftest import NS_A, TEST_DB_NAME, build_corpus_chunks
from tests.fakes import FakeGenerationService, FakeVectorStore

WS_OID = ObjectId()
OWNER_OID = ObjectId()
PATH = f"/api/workspaces/{WS_OID}/generate/text"
BODY = {"brief": "Write about hempcrete embodied carbon", "tone": "default", "length": "medium"}


class BlockingGenerationService(FakeGenerationService):
    """Yields one delta, then waits on an event that never fires. Records how its stream
    ended, so a test can tell it was closed rather than left for garbage collection."""

    def __init__(self) -> None:
        super().__init__()
        self.never = asyncio.Event()
        self.closed: list[tuple[str, bool]] = []
        self.lines: list[MeteredLine] = []

    async def stream_text(self, system: str, user: str, *, line: MeteredLine) -> AsyncGenerator[str, None]:
        self.calls.append((system, user))
        self.lines.append(line)
        line.mark_started()
        try:
            yield "Hempcrete "
            await self.never.wait()
            yield "never"
        except BaseException as exc:
            # Whether the route had already settled the line tells a close that reached
            # the model first (False) from a late one by the async-generator finalizer.
            self.closed.append((type(exc).__name__, line.settled))
            raise


class SteadyGenerationService(BlockingGenerationService):
    """Streams a delta every 5 ms, forever, so the send that finds the visitor gone is
    always a text frame (never a heartbeat)."""

    async def stream_text(self, system: str, user: str, *, line: MeteredLine) -> AsyncGenerator[str, None]:
        self.calls.append((system, user))
        self.lines.append(line)
        line.mark_started()
        try:
            while True:
                yield "Hempcrete "
                await asyncio.sleep(0.005)
        except BaseException as exc:
            # Whether the route had already settled the line tells a close that reached
            # the model first (False) from a late one by the async-generator finalizer.
            self.closed.append((type(exc).__name__, line.settled))
            raise


@pytest_asyncio.fixture
async def ready_app(test_db, monkeypatch):
    """The app with a ready workspace and a short heartbeat (so a 2.4 disconnect surfaces
    on the next send within the test). Returns a function that installs a model fake."""
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    await test_db.workspaces.insert_one(
        {
            "_id": WS_OID,
            "owner_id": OWNER_OID,
            "name": "Verdure",
            "slug": "verdure",
            "brand_profile": {"voice_summary": "Grounded, data-first voice.", "exemplars": []},
            "vector_namespace": NS_A,
            "embedding_model": settings.embedding_model,
            "embedding_dim": settings.embedding_dim,
            "asset_count": 5,
            "ready_chunk_count": 12,
            "created_at": utcnow(),
            "updated_at": utcnow(),
        }
    )
    store = FakeVectorStore()
    await store.upsert_chunks(NS_A, build_corpus_chunks(NS_A))
    monkeypatch.setattr(generate_mod, "get_vector_store", lambda: store)
    monkeypatch.setattr(generate_mod, "sse_response", functools.partial(sse_response, heartbeat_s=0.05))

    user = UserInDB(id=str(OWNER_OID), email="o@e.com", hashed_password="x", full_name="O")
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[get_current_user] = lambda: user

    def install(service: BlockingGenerationService) -> BlockingGenerationService:
        app.dependency_overrides[GenerationService] = lambda: service
        return service

    try:
        yield install
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def blocking(ready_app) -> BlockingGenerationService:
    return ready_app(BlockingGenerationService())


@pytest.fixture
def steady(ready_app) -> SteadyGenerationService:
    return ready_app(SteadyGenerationService())


def _scope(spec_version: str) -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": spec_version},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": PATH,
        "raw_path": PATH.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"test"), (b"content-type", b"application/json")],
        "client": ("127.0.0.1", 50000),
        "server": ("test", 80),
    }


async def _drive(spec_version: str, receive, send, service: BlockingGenerationService):
    """Run the app call to its end and snapshot, with no await in between, how the model's
    stream ended and whether its ledger lines settled. A snapshot taken later could be
    rescued by the async-generator finalizer, which closes an abandoned stream at some
    later loop turn. The call must end on its own: a timeout's cancellation would settle
    the line by itself and hide a stream that never noticed the visitor left."""

    async def call() -> tuple[list[tuple[str, bool]], list[bool]]:
        # 2.4: Starlette turns the OSError into ClientDisconnect, which leaves the app.
        with contextlib.suppress(ClientDisconnect):
            await app(_scope(spec_version), receive, send)
        return list(service.closed), [line.settled for line in service.lines]

    task = asyncio.ensure_future(call())
    done, _ = await asyncio.wait({task}, timeout=5)
    if not done:
        task.cancel()
        with contextlib.suppress(BaseException):
            await task
        pytest.fail("the stream never noticed the disconnect")
    return task.result()


def _request_receive(then):
    """A `receive` that returns the request body once, then defers to `then`."""
    read = False

    async def receive() -> dict:
        nonlocal read
        if not read:
            read = True
            return {"type": "http.request", "body": json.dumps(BODY).encode(), "more_body": False}
        return await then()

    return receive


async def _calls_by_purpose(db) -> dict[str, dict]:
    return {c["purpose"]: c for c in await db.ai_spend_calls.find({}).to_list(None)}


@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
async def test_a_disconnect_settles_the_reservation_at_the_reserved_amount(test_db, blocking, spec_version):
    body_sent = asyncio.Event()
    bodies: list[bytes] = []
    refused: list[bytes] = []

    async def after_request() -> dict:
        if spec_version == "2.3":
            await body_sent.wait()  # the visitor leaves once the first delta arrives
            return {"type": "http.disconnect"}
        await asyncio.Event().wait()  # 2.4 servers report a disconnect through send() instead
        raise AssertionError("unreachable")

    async def send(message: dict) -> None:
        if message["type"] != "http.response.body":
            return
        if spec_version == "2.4" and bodies:
            refused.append(message["body"])
            raise OSError("client went away")
        bodies.append(message["body"])
        body_sent.set()

    closed, settled = await _drive(spec_version, _request_receive(after_request), send, blocking)

    assert bodies[0] == b'data: {"text": "Hempcrete "}\n\n'
    if spec_version == "2.4":
        # The heartbeat is the send that found the visitor gone.
        assert refused == [HEARTBEAT.encode()]
    # The model's stream was closed by the disconnect, not left for garbage collection.
    assert closed in ([("CancelledError", False)], [("GeneratorExit", False)])
    assert settled == [True]

    calls = await _calls_by_purpose(test_db)
    assert set(calls) == {"retrieval", "text_post"}
    text_call = calls["text_post"]
    assert text_call["status"] == "settled"
    assert text_call["actual_micros"] == text_call["reserved_micros"]
    assert text_call["outcome"] == "canceled_or_unknown"
    retrieval = calls["retrieval"]
    assert (retrieval["status"], retrieval["outcome"]) == ("settled", "ok")
    # The fake embedder reports len(text) // 4 tokens.
    assert retrieval["actual_micros"] == embedding_cost_micros(settings.embedding_model, len(BODY["brief"]) // 4)
    # Nothing was persisted for a stream the visitor abandoned.
    assert await test_db.generations.count_documents({}) == 0


@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
async def test_a_disconnect_on_a_text_frame_closes_the_model_stream_at_once(test_db, steady, spec_version):
    """The model streams steadily, so the send that finds the visitor gone carries a text
    frame: 2.4 raises on it; 2.3 blocks in it until Starlette's cancel lands there."""
    send_stuck = asyncio.Event()
    bodies: list[bytes] = []
    failed: list[bytes] = []

    async def after_request() -> dict:
        if spec_version == "2.3":
            await send_stuck.wait()  # the disconnect arrives while a send is blocked
            return {"type": "http.disconnect"}
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(message: dict) -> None:
        if message["type"] != "http.response.body":
            return
        if bodies:
            failed.append(message["body"])
            if spec_version == "2.4":
                raise OSError("client went away")
            send_stuck.set()
            await asyncio.Event().wait()  # a dead peer: the write never completes
        bodies.append(message["body"])

    closed, settled = await _drive(spec_version, _request_receive(after_request), send, steady)

    assert failed == [b'data: {"text": "Hempcrete "}\n\n']
    assert closed in ([("CancelledError", False)], [("GeneratorExit", False)])
    assert settled == [True]
    text_call = (await _calls_by_purpose(test_db))["text_post"]
    assert text_call["status"] == "settled"
    assert text_call["actual_micros"] == text_call["reserved_micros"]
    assert text_call["outcome"] == "canceled_or_unknown"
    assert await test_db.generations.count_documents({}) == 0


@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
async def test_a_disconnect_before_the_stream_starts_releases_the_reservation(test_db, blocking, spec_version):
    """The visitor is gone before the body is first read: the response start never
    completes (2.3: the send blocks on a dead peer until Starlette's cancel lands there;
    2.4: the send raises). The route's event generator never starts, so its `finally`
    never runs; `on_close` still settles the line before the app call returns, and an
    unstarted call is released at 0."""
    send_stuck = asyncio.Event()

    async def after_request() -> dict:
        if spec_version == "2.3":
            await send_stuck.wait()
            return {"type": "http.disconnect"}
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(message: dict) -> None:
        assert message["type"] == "http.response.start"
        if spec_version == "2.4":
            raise OSError("client went away")
        send_stuck.set()
        await asyncio.Event().wait()

    await _drive(spec_version, _request_receive(after_request), send, blocking)

    # A never-started generator cannot settle later, so the ledger is read right here.
    assert blocking.calls == []
    calls = await _calls_by_purpose(test_db)
    text_call = calls["text_post"]
    assert (text_call["status"], text_call["actual_micros"], text_call["outcome"]) == (
        "settled",
        0,
        "not_attempted",
    )
    assert (calls["retrieval"]["status"], calls["retrieval"]["outcome"]) == ("settled", "ok")
