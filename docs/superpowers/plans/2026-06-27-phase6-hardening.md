# Phase 6 PR-B — Ingestion Safety + Generation Concurrency + Demo-Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ingestion bounded + retryable, make generation streams safe across workspace switches and stalls, and close the demo-guard gap on card-image upload.

**Architecture:** Three independent tracks. Server: parse off the event loop with a timeout (`asyncio.to_thread` + `wait_for`), cap chunk count (error, no upsert), add a demo-blocked `reingest` route, and `require_not_demo` on `upload_image`. Client: abort+reset each generation hook when the workspace changes, add a stream-inactivity timeout + type-guarded `onError` in `lib/sse.ts`, a Retry affordance on errored assets, and a Dashboard error state.

**Tech Stack:** FastAPI + Motor + asyncio (server); React + react-query + fetch/ReadableStream SSE (client). Tests: pytest + vitest.

**Spec:** `docs/superpowers/specs/2026-06-27-phase6-hardening-design.md`

**Working dir for server commands:** `server/` (venv `.venv/bin/...`, prefix model-touching runs with `env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY`). Branch: `feat/6-hardening` (already created off `dev`).

**Note — already done (no task):** "disable Generate while streaming" already ships — `ControlsPanel` computes `canGenerate = brief… && !isStreaming` and shows a Stop button, wired across all modes via `isStreaming`. PR-B does not touch it.

**Constants:** `PARSE_TIMEOUT_S = 30`, `MAX_CHUNKS = 400` (`ingestion_service`); `STREAM_INACTIVITY_MS = 30000` (`lib/sse.ts`).

**File structure:**
- `server/app/services/ingestion_service.py` — constants, `to_thread`+`wait_for` parse, chunk cap.
- `server/app/services/asset_service.py` — `mark_processing`.
- `server/app/routes/assets.py` — `POST /{asset_id}/reingest`.
- `server/app/routes/images.py` — `require_not_demo` on `upload_image`.
- `server/tests/test_ingestion_safety.py`, `server/tests/test_reingest_and_demo.py` (new).
- `client/src/lib/sse.ts` — export + timeout + type-guard; `client/src/lib/sse.test.ts` (new).
- `client/src/features/generate/use{Text,Card,PostPack,Document}Generation.ts` — abort/reset effect.
- `client/src/features/generate/useCardGeneration.test.tsx` — abort-on-switch (new).
- `client/src/api/assets.ts` — `useReingestAsset`; `client/src/features/assets/AssetsPage.tsx` — Retry.
- `client/src/features/dashboard/DashboardPage.tsx` — error banner.
- Docs: `docs/DECISIONS.md`, `docs/PLAN.md`, `CHANGELOG.md`.

---

### Task 1: Ingestion — bounded parse + chunk cap

**Files:**
- Modify: `server/app/services/ingestion_service.py`
- Test: `server/tests/test_ingestion_safety.py`

- [ ] **Step 1: Write the failing tests**

Create `server/tests/test_ingestion_safety.py`:

```python
"""Phase 6 PR-B — ingestion is bounded: a slow parse times out and an oversized
doc is rejected, both marking the asset `error` with nothing upserted."""
import time

import pytest
from bson import ObjectId

import app.services.ingestion_service as ing
from app.models.common import utcnow
from app.rag.loaders import Section
from tests.fakes import FakeVectorStore

NS = "ws-ns"


class _FakeStorage:
    def local_path(self, key: str) -> str:
        return "/tmp/unused"


async def _seed_asset(db) -> str:
    oid = ObjectId()
    now = utcnow()
    await db.assets.insert_one({
        "_id": oid, "workspace_id": ObjectId(), "filename": "big.md",
        "content_type": "text/markdown", "asset_kind": "other", "storage_key": "k",
        "size_bytes": 1, "ingestion_status": "processing", "chunk_count": 0,
        "error": None, "ingested_at": None, "created_at": now, "updated_at": now,
    })
    return str(oid)


@pytest.mark.asyncio
async def test_chunk_cap_rejects_oversized(test_db, monkeypatch):
    store = FakeVectorStore()

    async def _db():
        return test_db

    monkeypatch.setattr(ing, "get_database", _db)
    monkeypatch.setattr(ing, "get_storage", lambda: _FakeStorage())
    monkeypatch.setattr(ing, "get_vector_store", lambda: store)
    monkeypatch.setattr(ing, "load_sections", lambda path, ct: [Section(text="x", page=None)])
    monkeypatch.setattr(ing, "MAX_CHUNKS", 3)
    monkeypatch.setattr(ing, "build_chunks", lambda **kw: [{"id": f"a:{i}", "text": "t", "metadata": {}} for i in range(5)])

    asset_id = await _seed_asset(test_db)
    await ing.ingest_asset(asset_id, NS)

    doc = await test_db.assets.find_one({"_id": ObjectId(asset_id)})
    assert doc["ingestion_status"] == "error"
    assert "too large" in doc["error"].lower()
    assert await store.query(NS, "t") == []  # nothing upserted


@pytest.mark.asyncio
async def test_parse_timeout_marks_error(test_db, monkeypatch):
    async def _db():
        return test_db

    def _slow(path, ct):
        time.sleep(0.3)
        return []

    monkeypatch.setattr(ing, "get_database", _db)
    monkeypatch.setattr(ing, "get_storage", lambda: _FakeStorage())
    monkeypatch.setattr(ing, "get_vector_store", lambda: FakeVectorStore())
    monkeypatch.setattr(ing, "load_sections", _slow)
    monkeypatch.setattr(ing, "PARSE_TIMEOUT_S", 0.05)

    asset_id = await _seed_asset(test_db)
    await ing.ingest_asset(asset_id, NS)

    doc = await test_db.assets.find_one({"_id": ObjectId(asset_id)})
    assert doc["ingestion_status"] == "error"
    assert "timed out" in doc["error"].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_ingestion_safety.py -q`
Expected: FAIL — no timeout/cap yet (asset won't be `error`; `MAX_CHUNKS` may not exist).

- [ ] **Step 3: Edit `server/app/services/ingestion_service.py`**

Add `import asyncio` at the top (with the other imports). Add constants near `POSTS_KIND`:

```python
PARSE_TIMEOUT_S = 30
MAX_CHUNKS = 400
```

Replace the body of the `try:` block in `ingest_asset` (the parse → build → upsert section) with:

```python
    try:
        storage = get_storage()
        path = storage.local_path(asset["storage_key"])
        try:
            sections = await asyncio.wait_for(
                asyncio.to_thread(load_sections, path, asset["content_type"]),
                PARSE_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            await asset_service.mark_error(
                db, asset_oid, "Parsing timed out — try a smaller or simpler file."
            )
            return
        chunks = build_chunks(
            workspace_namespace=workspace_namespace,
            asset_id=asset_id,
            asset_kind=asset["asset_kind"],
            filename=asset["filename"],
            sections=sections,
        )
        if not chunks:
            await asset_service.mark_error(db, asset_oid, "No extractable text found in file.")
            return
        if len(chunks) > MAX_CHUNKS:
            await asset_service.mark_error(
                db,
                asset_oid,
                f"Document too large ({len(chunks)} sections > {MAX_CHUNKS}) — split it into smaller files.",
            )
            return
        count = await get_vector_store().upsert_chunks(workspace_namespace, chunks)
        marked = await asset_service.mark_ready(db, asset_oid, count)
        if marked is None:
            await get_vector_store().delete_asset(workspace_namespace, asset_id)
            logger.info("asset %s deleted mid-ingest; dropped %d orphan chunks", asset_id, count)
            return
        logger.info("ingested asset %s → %d chunks", asset_id, count)
    except Exception as exc:  # noqa: BLE001 — surface any failure as asset error state
        logger.exception("ingestion failed for asset %s", asset_id)
        await asset_service.mark_error(db, asset_oid, str(exc))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_ingestion_safety.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add server/app/services/ingestion_service.py server/tests/test_ingestion_safety.py
git commit -m "feat(ingestion): bounded parse (to_thread+timeout) + chunk-count cap"
```

---

### Task 2: `asset_service.mark_processing`

**Files:**
- Modify: `server/app/services/asset_service.py`
- (Covered by the reingest route test in Task 3.)

- [ ] **Step 1: Add `mark_processing`** to `server/app/services/asset_service.py` (after `mark_error`):

```python
async def mark_processing(db: AsyncIOMotorDatabase, asset_oid: ObjectId) -> Optional[dict]:
    """Reset an asset to `processing` for a re-ingest: clear the error and, if it
    was `ready`, decrement the workspace's ready-chunk count (a fresh ingest will
    re-add the new count). Returns the updated asset doc, or None if it's gone."""
    now = utcnow()
    doc = await db.assets.find_one({"_id": asset_oid})
    if not doc:
        return None
    if doc.get("ingestion_status") == IngestionStatus.ready.value:
        await db.workspaces.update_one(
            {"_id": doc["workspace_id"]},
            {"$inc": {"ready_chunk_count": -int(doc.get("chunk_count", 0))},
             "$set": {"updated_at": now}},
        )
    await db.assets.update_one(
        {"_id": asset_oid},
        {"$set": {"ingestion_status": IngestionStatus.processing.value,
                  "chunk_count": 0, "error": None, "ingested_at": None, "updated_at": now}},
    )
    return await db.assets.find_one({"_id": asset_oid})
```

- [ ] **Step 2: Lint/type check**

Run: `cd server && .venv/bin/ruff check app/services/asset_service.py && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/mypy app/services/asset_service.py`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add server/app/services/asset_service.py
git commit -m "feat(ingestion): mark_processing for re-ingest (resets state + counters)"
```

---

### Task 3: Reingest route + demo-guard on image upload

**Files:**
- Modify: `server/app/routes/assets.py`, `server/app/routes/images.py`
- Test: `server/tests/test_reingest_and_demo.py`

- [ ] **Step 1: Write the failing tests**

Create `server/tests/test_reingest_and_demo.py`:

```python
"""Phase 6 PR-B — reingest resets an errored asset (demo-blocked); the card-image
upload is demo-blocked, reconciling server with the UI."""
import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
from app.main import app
from app.models.common import utcnow
from app.models.user import UserInDB
from app.utils.dependencies import get_current_user, get_workspace_or_404
from tests.conftest import TEST_DB_NAME

WS = ObjectId()
OWNER = ObjectId()
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000a49444154789c6360000002000154a24f3f0000000049454e44ae426082"
)


def _user(is_demo: bool = False) -> UserInDB:
    return UserInDB(id=str(OWNER), email="o@example.com", hashed_password="x",
                    full_name="O", is_demo=is_demo)


def _workspace() -> dict:
    return {"_id": WS, "owner_id": OWNER, "vector_namespace": str(WS)}


async def _seed_errored_asset(db) -> str:
    oid = ObjectId()
    now = utcnow()
    await db.assets.insert_one({
        "_id": oid, "workspace_id": WS, "filename": "f.md", "content_type": "text/markdown",
        "asset_kind": "other", "storage_key": "k", "size_bytes": 1,
        "ingestion_status": "error", "chunk_count": 0, "error": "boom",
        "ingested_at": None, "created_at": now, "updated_at": now,
    })
    return str(oid)


async def _mk(test_db, monkeypatch, *, is_demo=False) -> AsyncClient:
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[get_current_user] = lambda: _user(is_demo)
    app.dependency_overrides[get_workspace_or_404] = lambda: _workspace()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def client(test_db, monkeypatch):
    ac = await _mk(test_db, monkeypatch)
    async with ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_reingest_resets_to_processing(client, test_db):
    asset_id = await _seed_errored_asset(test_db)
    resp = await client.post(f"/api/workspaces/{WS}/assets/{asset_id}/reingest")
    assert resp.status_code == 202
    assert resp.json()["ingestion_status"] == "processing"
    doc = await test_db.assets.find_one({"_id": ObjectId(asset_id)})
    assert doc["ingestion_status"] == "processing"
    assert doc["error"] is None


@pytest.mark.asyncio
async def test_reingest_missing_is_404(client):
    resp = await client.post(f"/api/workspaces/{WS}/assets/{ObjectId()}/reingest")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reingest_demo_blocked(test_db, monkeypatch):
    asset_id = await _seed_errored_asset(test_db)
    ac = await _mk(test_db, monkeypatch, is_demo=True)
    async with ac:
        resp = await ac.post(f"/api/workspaces/{WS}/assets/{asset_id}/reingest")
    app.dependency_overrides.clear()
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_image_upload_demo_blocked(test_db, monkeypatch):
    ac = await _mk(test_db, monkeypatch, is_demo=True)
    async with ac:
        resp = await ac.post(
            f"/api/workspaces/{WS}/images/upload",
            files={"file": ("c.png", PNG, "image/png")},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_reingest_and_demo.py -q`
Expected: FAIL — reingest 404 (route absent); image upload 201 (not yet guarded).

- [ ] **Step 3: Add the reingest route** in `server/app/routes/assets.py` (after `list_assets`, before `get_asset`):

```python
@router.post(
    "/{asset_id}/reingest", response_model=AssetResponse, status_code=status.HTTP_202_ACCEPTED
)
async def reingest_asset(
    asset_id: str,
    background_tasks: BackgroundTasks,
    workspace: dict = Depends(get_workspace_or_404),
    _: object = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Retry ingestion for an asset (typically one in `error`). Drops any prior
    vectors first so a re-parse can't orphan old chunks, resets to `processing`,
    and re-runs ingestion out of band."""
    doc = await asset_service.get_asset(db, workspace["_id"], asset_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    await get_vector_store().delete_asset(workspace["vector_namespace"], asset_id)
    updated = await asset_service.mark_processing(db, doc["_id"])
    background_tasks.add_task(ingest_asset, asset_id, workspace["vector_namespace"])
    return await asset_service.asset_response(updated)
```

- [ ] **Step 4: Add the demo guard** in `server/app/routes/images.py` — update the `upload_image` signature on `ws_router` to depend on `require_not_demo`:

Change its import line to include `require_not_demo`:

```python
from app.utils.dependencies import get_current_user, get_workspace_or_404, require_not_demo
```

And add the dependency to `upload_image`:

```python
@ws_router.post("/upload", response_model=ImageUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile,
    workspace: dict = Depends(get_workspace_or_404),
    _: object = Depends(require_not_demo),
):
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_reingest_and_demo.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add server/app/routes/assets.py server/app/routes/images.py server/tests/test_reingest_and_demo.py
git commit -m "feat(ingestion): demo-guarded reingest route + guard card-image upload"
```

---

### Task 4: Server gate

- [ ] **Step 1: ruff + mypy + full pytest**

Run: `cd server && .venv/bin/ruff check app tests && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/mypy app && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest -q`
Expected: ruff clean; mypy clean; all pass.

- [ ] **Step 2: Fix anything; commit if changed**

```bash
git add -A && git commit -m "chore(hardening): server gate green"
```

---

### Task 5: SSE — inactivity timeout + type-guarded onError

**Files:**
- Modify: `client/src/lib/sse.ts`
- Test: `client/src/lib/sse.test.ts`

- [ ] **Step 1: Write the failing test**

Create `client/src/lib/sse.test.ts`:

```typescript
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readFrames, STREAM_INACTIVITY_MS } from "./sse";

function fakeResponse(reader: Partial<ReadableStreamDefaultReader<Uint8Array>>) {
  return { body: { getReader: () => reader } } as unknown as Response;
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("readFrames", () => {
  it("fires onError + cancels when the stream stalls", async () => {
    const cancel = vi.fn();
    const reader = { read: () => new Promise(() => {}), cancel, releaseLock: vi.fn() };
    const onError = vi.fn();
    const p = readFrames(fakeResponse(reader), { onText: vi.fn(), onMeta: vi.fn(), onError });
    await vi.advanceTimersByTimeAsync(STREAM_INACTIVITY_MS + 10);
    await p;
    expect(onError).toHaveBeenCalledOnce();
    expect(cancel).toHaveBeenCalled();
  });

  it("type-guards a non-string error frame", async () => {
    const frame = new TextEncoder().encode('data: {"error": 123}\n\n');
    let sent = false;
    const reader = {
      read: () =>
        sent
          ? Promise.resolve({ done: true, value: undefined })
          : ((sent = true), Promise.resolve({ done: false, value: frame })),
      cancel: vi.fn(),
      releaseLock: vi.fn(),
    };
    const onError = vi.fn();
    await readFrames(fakeResponse(reader), { onText: vi.fn(), onMeta: vi.fn(), onError });
    expect(onError).toHaveBeenCalledWith("Generation failed.");
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd client && npx vitest run src/lib/sse.test.ts`
Expected: FAIL — `readFrames`/`STREAM_INACTIVITY_MS` not exported; no timeout.

- [ ] **Step 3: Edit `client/src/lib/sse.ts`**

Add the constant near the top (after the imports):

```typescript
export const STREAM_INACTIVITY_MS = 30000;
```

Change `async function readFrames` to `export async function readFrames`, and replace its read loop so each `read()` races an inactivity timer and the error frame is type-guarded:

```typescript
export async function readFrames<Meta>(
  response: Response,
  handlers: StreamHandlers<Meta>,
): Promise<void> {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      let timer: ReturnType<typeof setTimeout>;
      const timeout = new Promise<"timeout">((resolve) => {
        timer = setTimeout(() => resolve("timeout"), STREAM_INACTIVITY_MS);
      });
      let result: Awaited<ReturnType<typeof reader.read>> | "timeout";
      try {
        result = await Promise.race([reader.read(), timeout]);
      } finally {
        clearTimeout(timer!);
      }
      if (result === "timeout") {
        await reader.cancel();
        handlers.onError("The stream stalled — try again.");
        return;
      }
      const { done, value } = result;
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const boundary = /\r?\n\r?\n/;
      let match: RegExpExecArray | null;
      while ((match = boundary.exec(buffer)) !== null) {
        const rawFrame = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        const line = rawFrame.replace(/^data:\s?/, "").replace(/\r$/, "");
        if (line === "[DONE]") return;
        if (!line) continue;
        try {
          const payload = JSON.parse(line);
          if ("text" in payload) handlers.onText((payload as SSETextFrame).text);
          else if ("meta" in payload) handlers.onMeta((payload as { meta: Meta }).meta);
          else if ("error" in payload)
            handlers.onError(typeof payload.error === "string" ? payload.error : "Generation failed.");
        } catch {
          /* ignore malformed frame */
        }
      }
    }
  } catch (err) {
    if ((err as Error).name !== "AbortError") handlers.onError("Stream interrupted.");
  } finally {
    reader.releaseLock();
  }
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd client && npx vitest run src/lib/sse.test.ts`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add client/src/lib/sse.ts client/src/lib/sse.test.ts
git commit -m "feat(sse): stream inactivity timeout + type-guarded onError"
```

---

### Task 6: Generation hooks — abort + reset on workspace switch

**Files:**
- Modify: `client/src/features/generate/use{Text,Card,PostPack,Document}Generation.ts`
- Test: `client/src/features/generate/useCardGeneration.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `client/src/features/generate/useCardGeneration.test.tsx`:

```tsx
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// Capture the AbortSignal handed to the stream; never resolve (stay in-flight).
const { streamCard, captured } = vi.hoisted(() => ({
  streamCard: vi.fn(),
  captured: { signal: undefined as AbortSignal | undefined },
}));
vi.mock("@/lib/sse", () => ({
  streamCardGeneration: (_ws: string, _body: unknown, _h: unknown, signal?: AbortSignal) => {
    captured.signal = signal;
    streamCard();
    return new Promise(() => {});
  },
}));
vi.mock("@/api/images", () => ({ fetchImageDataUrl: vi.fn(), trackUnsplashDownload: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: { patch: vi.fn() } }));

import { useCardGeneration } from "./useCardGeneration";

let latest: ReturnType<typeof useCardGeneration>;
let container: HTMLDivElement;
let root: Root;

function Harness({ ws }: { ws: string }) {
  latest = useCardGeneration(ws);
  return null;
}

beforeEach(() => {
  container = document.createElement("div");
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.clearAllMocks();
});

describe("useCardGeneration abort-on-switch", () => {
  it("aborts the in-flight stream and resets when workspace changes", () => {
    act(() => root.render(<Harness ws="a" />));
    act(() => {
      void latest.generate({ brief: "x", template_id: "photo-led", tone: "default" });
    });
    expect(latest.status).toBe("streaming");
    const signal = captured.signal!;
    act(() => root.render(<Harness ws="b" />));
    expect(signal.aborted).toBe(true);
    expect(latest.status).toBe("idle");
  });
});
```

(If `useCardGeneration` returns `state` nested, adjust `latest.status`/`latest.generate` to the real shape — check the hook's return object before running.)

- [ ] **Step 2: Run it to verify it fails**

Run: `cd client && npx vitest run src/features/generate/useCardGeneration.test.tsx`
Expected: FAIL — switching workspace neither aborts nor resets.

- [ ] **Step 3: Add the effect to each hook.**

In `useCardGeneration.ts` and `usePostPackGeneration.ts` (both already import `useEffect`), after the `abortRef` declaration:

```typescript
  useEffect(() => {
    setState(initial("photo-led"));
    return () => abortRef.current?.abort();
  }, [workspaceId]);
```

In `useTextGeneration.ts` and `useDocumentGeneration.ts`, add `useEffect` to the React import, then after `abortRef`:

```typescript
  useEffect(() => {
    setState(INITIAL);
    return () => abortRef.current?.abort();
  }, [workspaceId]);
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd client && npx vitest run src/features/generate/useCardGeneration.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add client/src/features/generate/useTextGeneration.ts client/src/features/generate/useCardGeneration.ts client/src/features/generate/usePostPackGeneration.ts client/src/features/generate/useDocumentGeneration.ts client/src/features/generate/useCardGeneration.test.tsx
git commit -m "feat(generate): abort + reset the stream on workspace switch"
```

---

### Task 7: Reingest API + Retry button + Dashboard error state

**Files:**
- Modify: `client/src/api/assets.ts`, `client/src/features/assets/AssetsPage.tsx`, `client/src/features/dashboard/DashboardPage.tsx`

- [ ] **Step 1: Add `useReingestAsset`** to `client/src/api/assets.ts` (after `useDeleteAsset`):

```typescript
export function useReingestAsset(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (assetId: string) =>
      (await api.post<Asset>(`/workspaces/${workspaceId}/assets/${assetId}/reingest`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["assets", workspaceId] }),
  });
}
```

- [ ] **Step 2: Add the Retry button** in `client/src/features/assets/AssetsPage.tsx` `AssetRow`. Import the hook (extend the existing `@/api/assets` import to include `useReingestAsset`), then inside `AssetRow` add `const reingest = useReingestAsset(workspaceId);` and, where the error message renders (`asset.ingestion_status === "error" && asset.error`), add a Retry control next to it (only for non-demo, mirroring `canDelete`):

```tsx
{asset.ingestion_status === "error" && canDelete && (
  <Button
    size="sm"
    variant="ghost"
    onClick={() => reingest.mutate(asset.id)}
    loading={reingest.isPending}
  >
    Retry
  </Button>
)}
```

(Ensure `Button` is imported in the file — it is, used by `UploadCard`.)

- [ ] **Step 3: Add the Dashboard error state** in `client/src/features/dashboard/DashboardPage.tsx`. Pull `isError` from the workspace hook and short-circuit:

```tsx
const { workspace, workspaceId, isError } = useActiveWorkspace();
```

After the header, before the stat grid:

```tsx
{isError && (
  <div className="rounded-lg border border-border bg-surface p-4 text-sm text-destructive">
    Couldn't load this workspace. Is the server running?
  </div>
)}
```

(`useActiveWorkspace` already returns `isError`.)

- [ ] **Step 4: Typecheck + lint + format**

Run: `cd client && npx tsc --noEmit && npx eslint src && npx prettier --write "src/**/*.{ts,tsx}"`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add client/src/api/assets.ts client/src/features/assets/AssetsPage.tsx client/src/features/dashboard/DashboardPage.tsx
git commit -m "feat(hardening): asset Retry (reingest) + Dashboard error state"
```

---

### Task 8: Client gate

- [ ] **Step 1: tsc + eslint + prettier + vitest + build**

Run: `cd client && npx tsc --noEmit && npx eslint src && npx prettier --check "src/**/*.{ts,tsx}" && npx vitest run && npx vite build`
Expected: all green.

- [ ] **Step 2: Fix anything; commit if changed**

```bash
git add -A && git commit -m "chore(hardening): client gate green"
```

---

### Task 9: Docs

**Files:** `docs/DECISIONS.md`, `docs/PLAN.md`, `CHANGELOG.md`

- [ ] **Step 1: DECISIONS** — add entry #26: Phase 6 PR-B — ingestion is **bounded** (parse off-loop via `asyncio.to_thread` + `PARSE_TIMEOUT_S=30`; **chunk cap `MAX_CHUNKS=400` → error, not truncation**) with a **demo-blocked `reingest`/Retry** path (drops prior vectors first); generation streams **abort + reset on workspace switch**, get a **`STREAM_INACTIVITY_MS=30000` inactivity timeout** + **type-guarded SSE `onError`** ("disable Generate while streaming" already shipped); **demo-guard reconciled** — `require_not_demo` on the card-image upload; Dashboard gains an error state. Completes Phase 6.

- [ ] **Step 2: PLAN.md** — under "Phase 6 — Robustness", mark PR-B built; note Phase 6 complete.

- [ ] **Step 3: CHANGELOG.md** — add "Phase 6: Robustness — `0.8.0` *(PR-B: ingestion safety + concurrency + demo-guard)*" under `[Unreleased]`: bounded/retryable ingestion, stream abort-on-switch + inactivity timeout + type-guarded onError, demo-guarded image upload, Dashboard error state; tests (pytest +N, vitest +N).

- [ ] **Step 4: Commit**

```bash
git add docs/DECISIONS.md docs/PLAN.md CHANGELOG.md
git commit -m "docs(phase-6): PR-B hardening — DECISIONS/PLAN/CHANGELOG"
```

---

### Task 10: Review, verify, PR

- [ ] **Step 1: Re-run both gates** (Task 4 + Task 8) — confirm green.
- [ ] **Step 2: `/code-review`** the branch diff; fix real findings.
- [ ] **Step 3: `/security-review`**; fix real findings. (Surface: the demo-guard fix is itself a security tightening; reingest is ownership + demo guarded; the parse timeout bounds an untrusted-file DoS vector.)
- [ ] **Step 4: Live verify (owner):** upload a garbage/oversized file → asset shows a friendly error + Retry → Retry re-runs; start a generation then switch workspace → stream cancels + clean Generate page; demo user can't upload a card image.
- [ ] **Step 5: Owner commit/push approval**, then push `feat/6-hardening` and open a PR into `dev` (REST API + keychain token; no `gh`). Update `bcs-phase-state` memory when it merges (Phase 6 complete).

---

## Self-Review

**Spec coverage:** non-blocking + parse timeout (Task 1) ✓; chunk cap → error, no upsert (Task 1) ✓; reingest/Retry, drops prior vectors + demo-blocked (Tasks 2,3,7) ✓; `mark_processing` resets state + counters (Task 2) ✓; abort+reset on workspace switch, all 4 hooks (Task 6) ✓; stream inactivity timeout (Task 5) ✓; type-guarded `onError` (Task 5) ✓; demo-guard on `upload_image` (Task 3) ✓; Dashboard error state (Task 7) ✓; "disable Generate while streaming" — already shipped, noted (no task) ✓; tests pytest + vitest (throughout) ✓; docs (Task 9) ✓.

**Placeholder scan:** none — every code step is concrete; doc steps describe specific edits mirroring existing entries.

**Type consistency:** constants `PARSE_TIMEOUT_S`/`MAX_CHUNKS` (Task 1) match the timeout/cap tests (Task 1) and are monkeypatched by name. `mark_processing(db, asset_oid)` (Task 2) matches the reingest route call (Task 3). `reingest` route path `/{asset_id}/reingest` matches `useReingestAsset` (Task 7) and the tests (Task 3). `STREAM_INACTIVITY_MS` + exported `readFrames` (Task 5) match the sse test (Task 5). The abort effect uses each hook's own `initial(...)`/`INITIAL` (Task 6) as they're actually defined (card/postpack = `initial("photo-led")`, text/document = `INITIAL`). `require_not_demo` already exists in `app.utils.dependencies` (used elsewhere).
