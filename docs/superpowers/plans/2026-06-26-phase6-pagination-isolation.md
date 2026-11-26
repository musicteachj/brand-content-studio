# Phase 6 PR-A — Pagination + Isolation Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bound the unbounded History/Assets lists with limit+offset "Load more" pagination, and add an HTTP-level test proving one owner can't read another's workspace data.

**Architecture:** The two list services gain `limit`/`offset` and return `(items, next_offset)` via a `limit+1` sentinel (no `count()` on the hot path); routes return a `{items, next_offset}` envelope. Clients move to `useInfiniteQuery` with a "Load more" button. A small generation-count endpoint backs the dashboard stat (which needed a total, not a page). One new pytest asserts cross-owner 404s end-to-end.

**Tech Stack:** FastAPI + Motor + Pydantic v2 (server); React + Vite + TS + @tanstack/react-query `useInfiniteQuery` (client). Tests: pytest + vitest.

**Spec:** `docs/superpowers/specs/2026-06-26-phase6-pagination-isolation-design.md`

**Working dir for server commands:** `server/` (venv `.venv/bin/...`, prefix model-touching runs with `env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY`). Branch: `feat/6-pagination` (already created off `dev`).

**File structure:**
- `server/app/models/generation.py` — `GenerationPage`, `GenerationCount`.
- `server/app/models/asset.py` — `AssetPage`.
- `server/app/services/generations_service.py` — paginate `list_generations`; add `count_generations`.
- `server/app/services/asset_service.py` — paginate `list_assets`.
- `server/app/routes/generations.py` — list returns `GenerationPage`; new `GET /count`.
- `server/app/routes/assets.py` — list returns `AssetPage`.
- `server/tests/test_pagination.py`, `server/tests/test_isolation.py` (new).
- `client/src/types/index.ts` — `GenerationPage`, `AssetPage` types.
- `client/src/api/generations.ts`, `client/src/api/assets.ts` — infinite queries + count + `flattenPages`.
- `client/src/features/{history/HistoryPage,assets/AssetsPage,dashboard/DashboardPage}.tsx`.
- `client/src/api/pagination.ts` (+ `.test.ts`) — `flattenPages` helper.
- Docs: `docs/DECISIONS.md`, `docs/PLAN.md`, `CHANGELOG.md`.

---

### Task 1: Page + count models

**Files:**
- Modify: `server/app/models/generation.py`, `server/app/models/asset.py`
- Test: `server/tests/test_pagination.py`

- [ ] **Step 1: Write the failing test**

Create `server/tests/test_pagination.py`:

```python
"""Phase 6 PR-A — pagination of History/Assets lists."""
from app.models.asset import AssetPage
from app.models.generation import GenerationCount, GenerationPage


def test_page_models_shape():
    gp = GenerationPage(items=[], next_offset=24)
    assert gp.next_offset == 24
    assert AssetPage(items=[], next_offset=None).next_offset is None
    assert GenerationCount(count=7).count == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && .venv/bin/python -m pytest tests/test_pagination.py -q`
Expected: FAIL — `ImportError: cannot import name 'GenerationPage'`.

- [ ] **Step 3: Add models**

In `server/app/models/generation.py`, after `GenerationResponse`:

```python
class GenerationPage(BaseModel):
    items: list[GenerationResponse]
    next_offset: Optional[int] = None


class GenerationCount(BaseModel):
    count: int
```

(If `Optional` isn't imported there, add `from typing import Optional`.)

In `server/app/models/asset.py`, after `AssetResponse`:

```python
class AssetPage(BaseModel):
    items: list[AssetResponse]
    next_offset: Optional[int] = None
```

(Add `from typing import Optional` if missing.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && .venv/bin/python -m pytest tests/test_pagination.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add server/app/models/generation.py server/app/models/asset.py server/tests/test_pagination.py
git commit -m "feat(pagination): page + count models"
```

---

### Task 2: Paginate the list services + generation count

**Files:**
- Modify: `server/app/services/generations_service.py`, `server/app/services/asset_service.py`
- Test: `server/tests/test_pagination.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_pagination.py`)

```python
import pytest
import pytest_asyncio
from bson import ObjectId

from app.models.common import utcnow
from app.services import asset_service, generations_service
from tests.conftest import TEST_DB_NAME  # noqa: F401  (ensures conftest import)

WS = ObjectId()


async def _seed_generations(db, n):
    now = utcnow()
    docs = [
        {
            "_id": ObjectId(), "workspace_id": WS, "owner_id": ObjectId(), "type": "text",
            "brief": f"brief {i}", "status": "complete",
            "output": {"post_text": f"p{i}", "hashtags": [], "char_count": 2},
            "retrieved_chunk_ids": [], "retrieval_meta": [], "model": "m",
            "embedding_query_model": "e", "created_at": now, "updated_at": now,
        }
        for i in range(n)
    ]
    await db.generations.insert_many(docs)


@pytest.mark.asyncio
async def test_list_generations_paginates(test_db):
    await _seed_generations(test_db, 30)
    items, next_offset = await generations_service.list_generations(
        test_db, WS, "all", limit=24, offset=0
    )
    assert len(items) == 24
    assert next_offset == 24
    items2, next2 = await generations_service.list_generations(
        test_db, WS, "all", limit=24, offset=24
    )
    assert len(items2) == 6
    assert next2 is None


@pytest.mark.asyncio
async def test_count_generations(test_db):
    await _seed_generations(test_db, 5)
    assert await generations_service.count_generations(test_db, WS) == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_pagination.py -q`
Expected: FAIL — `list_generations` takes no `limit`.

- [ ] **Step 3: Update `generations_service.list_generations` + add count**

Replace `list_generations` in `server/app/services/generations_service.py`:

```python
async def list_generations(
    db: AsyncIOMotorDatabase,
    workspace_oid: ObjectId,
    type_filter: str = "all",
    *,
    limit: int = 24,
    offset: int = 0,
) -> tuple[list[GenerationResponse], Optional[int]]:
    query: dict = {"workspace_id": workspace_oid}
    if type_filter in ("text", "card", "document", "post_pack"):
        query["type"] = type_filter
    # Fetch one extra to detect a further page without a count().
    cursor = db.generations.find(query).sort("created_at", -1).skip(offset).limit(limit + 1)
    docs = [doc async for doc in cursor]
    has_more = len(docs) > limit
    items = [_to_response(d) for d in docs[:limit]]
    return items, (offset + limit if has_more else None)


async def count_generations(db: AsyncIOMotorDatabase, workspace_oid: ObjectId) -> int:
    return await db.generations.count_documents({"workspace_id": workspace_oid})
```

(Ensure `from typing import Optional` is imported in that file.)

- [ ] **Step 4: Update `asset_service.list_assets`**

Replace `list_assets` in `server/app/services/asset_service.py`:

```python
async def list_assets(
    db: AsyncIOMotorDatabase, workspace_oid: ObjectId, *, limit: int = 30, offset: int = 0
) -> tuple[list[AssetResponse], Optional[int]]:
    cursor = db.assets.find({"workspace_id": workspace_oid}).sort("created_at", -1).skip(offset).limit(limit + 1)
    docs = [doc async for doc in cursor]
    has_more = len(docs) > limit
    items = [_to_response(d) for d in docs[:limit]]
    return items, (offset + limit if has_more else None)
```

(Ensure `from typing import Optional` is imported.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_pagination.py -q`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add server/app/services/generations_service.py server/app/services/asset_service.py server/tests/test_pagination.py
git commit -m "feat(pagination): limit/offset list services + count_generations"
```

---

### Task 3: Routes — envelope responses + count endpoint

**Files:**
- Modify: `server/app/routes/generations.py`, `server/app/routes/assets.py`
- Test: `server/tests/test_pagination.py`

- [ ] **Step 1: Write the failing route test** (append to `tests/test_pagination.py`)

```python
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
from app.main import app
from app.utils.dependencies import get_workspace_or_404

GEN_URL = f"/api/workspaces/{WS}/generations"


@pytest_asyncio.fixture
async def client(test_db, monkeypatch):
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[get_workspace_or_404] = lambda: {"_id": WS, "owner_id": ObjectId()}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_generations_route_paginates(client, test_db):
    await _seed_generations(test_db, 30)
    r1 = await client.get(GEN_URL, params={"limit": 24, "offset": 0})
    assert r1.status_code == 200
    body = r1.json()
    assert len(body["items"]) == 24 and body["next_offset"] == 24
    r2 = await client.get(GEN_URL, params={"limit": 24, "offset": 24})
    assert len(r2.json()["items"]) == 6 and r2.json()["next_offset"] is None


@pytest.mark.asyncio
async def test_generations_count_route(client, test_db):
    await _seed_generations(test_db, 3)
    r = await client.get(f"{GEN_URL}/count")
    assert r.status_code == 200 and r.json()["count"] == 3


@pytest.mark.asyncio
async def test_limit_over_max_is_422(client):
    r = await client.get(GEN_URL, params={"limit": 1000})
    assert r.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_pagination.py -q`
Expected: FAIL — response is a bare list, no `items`/`next_offset`; `/count` 404s (matched by `/{generation_id}`).

- [ ] **Step 3: Update `routes/generations.py`**

Add imports: `GenerationPage, GenerationCount` to the `app.models.generation` import line.

Replace the list route, and add the count route **before** the `GET /{generation_id}` route (literal path must be declared first or it'll be captured by the id param):

```python
@router.get("", response_model=GenerationPage)
async def list_generations(
    type: str = Query("all", pattern="^(all|text|card|document|post_pack)$"),
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
    workspace: dict = Depends(get_workspace_or_404),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    items, next_offset = await generations_service.list_generations(
        db, workspace["_id"], type, limit=limit, offset=offset
    )
    return GenerationPage(items=items, next_offset=next_offset)


@router.get("/count", response_model=GenerationCount)
async def count_generations(
    workspace: dict = Depends(get_workspace_or_404),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    return GenerationCount(count=await generations_service.count_generations(db, workspace["_id"]))
```

- [ ] **Step 4: Update `routes/assets.py`**

Add `AssetPage` to the `app.models.asset` import line, add `Query` to the `fastapi` import, and replace the list route:

```python
@router.get("", response_model=AssetPage)
async def list_assets(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    workspace: dict = Depends(get_workspace_or_404),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    items, next_offset = await asset_service.list_assets(
        db, workspace["_id"], limit=limit, offset=offset
    )
    return AssetPage(items=items, next_offset=next_offset)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_pagination.py -q`
Expected: PASS (all pagination tests).

- [ ] **Step 6: Commit**

```bash
git add server/app/routes/generations.py server/app/routes/assets.py server/tests/test_pagination.py
git commit -m "feat(pagination): envelope list responses + generations count route"
```

---

### Task 4: HTTP cross-workspace isolation test

**Files:**
- Create: `server/tests/test_isolation.py`

- [ ] **Step 1: Write the test**

Create `server/tests/test_isolation.py`:

```python
"""Phase 6 PR-A — end-to-end tenancy: owner A's token cannot read owner B's
workspace data. Complements the unit-level test_query_is_workspace_scoped."""
import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
from app.main import app
from app.models.user import UserInDB
from app.utils.dependencies import get_current_user
from tests.conftest import TEST_DB_NAME

OWNER_A = ObjectId()
OWNER_B = ObjectId()
WS_B = ObjectId()


def _user_a() -> UserInDB:
    return UserInDB(id=str(OWNER_A), email="a@example.com", hashed_password="x", full_name="A")


async def _seed_ws_b(db):
    await db.workspaces.insert_one({
        "_id": WS_B, "owner_id": OWNER_B, "name": "B", "slug": "b", "brand_profile": {},
        "vector_namespace": str(WS_B), "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim, "asset_count": 0, "ready_chunk_count": 0,
    })
    await db.assets.insert_one({"_id": ObjectId(), "workspace_id": WS_B, "filename": "b.md",
                                "content_type": "text/markdown", "asset_kind": "other",
                                "storage_key": "k", "size_bytes": 1, "ingestion_status": "ready",
                                "chunk_count": 1, "error": None, "ingested_at": None,
                                "created_at": None, "updated_at": None})


@pytest_asyncio.fixture
async def client_a(test_db, monkeypatch):
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    await _seed_ws_b(test_db)
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[get_current_user] = lambda: _user_a()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.parametrize("path", ["", "/assets", "/generations", "/templates"])
@pytest.mark.asyncio
async def test_owner_a_cannot_read_owner_b(client_a, path):
    resp = await client_a.get(f"/api/workspaces/{WS_B}{path}")
    assert resp.status_code == 404  # never B's data leaked
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_isolation.py -q`
Expected: PASS (4 parametrized cases) — `get_workspace_or_404` already 404s a non-owner.

- [ ] **Step 3: Commit**

```bash
git add server/tests/test_isolation.py
git commit -m "test(isolation): HTTP cross-owner 404s on assets/generations/templates"
```

---

### Task 5: Server gate

- [ ] **Step 1: ruff + mypy + full pytest**

Run: `cd server && .venv/bin/ruff check app tests && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/mypy app && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest -q`
Expected: ruff clean; mypy clean; all pass.

- [ ] **Step 2: Fix anything; commit if changed**

```bash
git add -A && git commit -m "chore(pagination): server gate green"
```

---

### Task 6: Client — types, infinite queries, count, flatten helper

**Files:**
- Modify: `client/src/types/index.ts`, `client/src/api/generations.ts`, `client/src/api/assets.ts`
- Create: `client/src/api/pagination.ts` (+ `.test.ts`)

- [ ] **Step 1: Add types** to `client/src/types/index.ts`:

```typescript
export interface GenerationPage {
  items: Generation[];
  next_offset: number | null;
}

export interface AssetPage {
  items: Asset[];
  next_offset: number | null;
}
```

- [ ] **Step 2: Write the failing flatten-helper test**

Create `client/src/api/pagination.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { flattenPages } from "./pagination";

describe("flattenPages", () => {
  it("concatenates page items in order", () => {
    const data = { pages: [{ items: [1, 2] }, { items: [3] }] };
    expect(flattenPages(data)).toEqual([1, 2, 3]);
  });
  it("returns [] for undefined data", () => {
    expect(flattenPages<number>(undefined)).toEqual([]);
  });
});
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd client && npx vitest run src/api/pagination.test.ts`
Expected: FAIL — cannot find module `./pagination`.

- [ ] **Step 4: Create `client/src/api/pagination.ts`**

```typescript
/** Flatten react-query infinite-query pages into a single list. */
export function flattenPages<T>(data?: { pages: { items: T[] }[] }): T[] {
  return data?.pages.flatMap((p) => p.items) ?? [];
}
```

- [ ] **Step 5: Run it to verify it passes**

Run: `cd client && npx vitest run src/api/pagination.test.ts`
Expected: PASS (2 passed).

- [ ] **Step 6: Convert `api/generations.ts`** — replace `useGenerations` and add `useGenerationCount`:

```typescript
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Generation, GenerationPage, GenerationType } from "@/types";

export type HistoryFilter = "all" | GenerationType;

const HISTORY_LIMIT = 24;

export function useGenerations(workspaceId: string | null, filter: HistoryFilter = "all") {
  return useInfiniteQuery({
    queryKey: ["generations", workspaceId, filter],
    enabled: !!workspaceId,
    initialPageParam: 0,
    queryFn: async ({ pageParam }) =>
      (
        await api.get<GenerationPage>(`/workspaces/${workspaceId}/generations`, {
          params: { type: filter, limit: HISTORY_LIMIT, offset: pageParam },
        })
      ).data,
    getNextPageParam: (lastPage) => lastPage.next_offset ?? undefined,
  });
}

export function useGenerationCount(workspaceId: string | null) {
  return useQuery({
    queryKey: ["generations-count", workspaceId],
    enabled: !!workspaceId,
    queryFn: async () =>
      (await api.get<{ count: number }>(`/workspaces/${workspaceId}/generations/count`)).data.count,
  });
}
```

Keep the existing `useGeneration` and `useDeleteGeneration`; in `useDeleteGeneration.onSuccess`, also invalidate the count:

```typescript
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["generations", workspaceId] });
      qc.invalidateQueries({ queryKey: ["generations-count", workspaceId] });
    },
```

- [ ] **Step 7: Convert `api/assets.ts`** — replace `useAssets`:

```typescript
import { useInfiniteQuery } from "@tanstack/react-query";
// ...existing imports (useMutation, useQueryClient, api, types)...
import type { AssetPage } from "@/types";

const ASSETS_LIMIT = 30;

export function useAssets(workspaceId: string | null) {
  return useInfiniteQuery({
    queryKey: ["assets", workspaceId],
    enabled: !!workspaceId,
    initialPageParam: 0,
    queryFn: async ({ pageParam }) =>
      (
        await api.get<AssetPage>(`/workspaces/${workspaceId}/assets`, {
          params: { limit: ASSETS_LIMIT, offset: pageParam },
        })
      ).data,
    getNextPageParam: (lastPage) => lastPage.next_offset ?? undefined,
    // Poll while any *loaded* asset is processing (newly uploaded assets sort to
    // the first page, so the poll catches them).
    refetchInterval: (q) =>
      (q.state.data?.pages.some((p) => p.items.some((a) => a.ingestion_status === "processing"))
        ? 2500
        : false),
  });
}
```

(Keep `useUploadAsset`/`useDeleteAsset`; their existing `invalidateQueries(["assets", workspaceId])` still applies.)

- [ ] **Step 8: Typecheck**

Run: `cd client && npx tsc --noEmit`
Expected: errors in HistoryPage/AssetsPage/DashboardPage (next task) — the api files themselves compile.

- [ ] **Step 9: Commit**

```bash
git add client/src/types/index.ts client/src/api/pagination.ts client/src/api/pagination.test.ts client/src/api/generations.ts client/src/api/assets.ts
git commit -m "feat(pagination): client infinite queries + count + flatten helper"
```

---

### Task 7: Client — History, Assets, Dashboard pages

**Files:**
- Modify: `client/src/features/history/HistoryPage.tsx`, `client/src/features/assets/AssetsPage.tsx`, `client/src/features/dashboard/DashboardPage.tsx`

- [ ] **Step 1: HistoryPage** — consume the infinite query. Replace the destructure and list usage:

```typescript
import { flattenPages } from "@/api/pagination";
// ...
const {
  data,
  isLoading,
  isError,
  fetchNextPage,
  hasNextPage,
  isFetchingNextPage,
} = useGenerations(workspaceId, filter);
const generations = flattenPages(data);
```

Where the grid renders (`generations.map(...)`), keep it as-is (now an array). After the grid, add a Load-more control:

```tsx
{hasNextPage && (
  <div className="mt-6 flex justify-center">
    <Button variant="secondary" onClick={() => fetchNextPage()} loading={isFetchingNextPage}>
      Load more
    </Button>
  </div>
)}
```

(`generations.length === 0 && <EmptyHistory />` and the loading/error branches keep working — `generations` is an array; gate the empty state on `!isLoading`.)

- [ ] **Step 2: AssetsPage** — same pattern:

```typescript
import { flattenPages } from "@/api/pagination";
// ...
const { data, isLoading, isError, fetchNextPage, hasNextPage, isFetchingNextPage } =
  useAssets(workspaceId);
const assets = flattenPages(data);
const processing = assets.some((a) => a.ingestion_status === "processing");
```

The header count `({assets.length})` stays (shows loaded count). After the list, add the same Load-more block (gated on `hasNextPage`). The `processing` poll now lives in the query's `refetchInterval`; if a local `useEffect`/interval drove polling before, remove it (react-query handles it).

- [ ] **Step 3: DashboardPage** — use the count hook:

```typescript
import { useGenerationCount } from "@/api/generations";
// ...
const { data: generationCount } = useGenerationCount(workspaceId);
// ...
value={String(generationCount ?? 0)}
```

Remove the old `useGenerations` import/usage from DashboardPage.

- [ ] **Step 4: Typecheck + lint + format**

Run: `cd client && npx tsc --noEmit && npx eslint src && npx prettier --write "src/**/*.{ts,tsx}"`
Expected: clean (prettier writes).

- [ ] **Step 5: Commit**

```bash
git add client/src/features/history/HistoryPage.tsx client/src/features/assets/AssetsPage.tsx client/src/features/dashboard/DashboardPage.tsx
git commit -m "feat(pagination): Load more on History/Assets; Dashboard uses count"
```

---

### Task 8: Client gate

- [ ] **Step 1: tsc + eslint + prettier + vitest + build**

Run: `cd client && npx tsc --noEmit && npx eslint src && npx prettier --check "src/**/*.{ts,tsx}" && npx vitest run && npx vite build`
Expected: all green.

- [ ] **Step 2: Fix anything; commit if changed**

```bash
git add -A && git commit -m "chore(pagination): client gate green"
```

---

### Task 9: Docs

**Files:** `docs/DECISIONS.md`, `docs/PLAN.md`, `CHANGELOG.md`

- [ ] **Step 1: DECISIONS** — add entry #25: Phase 6 PR-A — History/Assets paginated with **limit+offset "Load more"** (envelope `{items, next_offset}`, `limit+1` sentinel, max 100; defaults 24/30); dashboard stat backed by a dedicated **generations count** endpoint; **HTTP cross-owner isolation** test added (complements the unit retrieval-isolation test). PR-B (ingestion caps + concurrency + demo-guard reconcile) is the next Phase 6 slice.

- [ ] **Step 2: PLAN.md** — under "Phase 6 — Robustness", note PR-A (pagination + isolation test) built; PR-B (ingestion safety + concurrency/states + demo-guard reconcile) pending.

- [ ] **Step 3: CHANGELOG.md** — add a "Phase 6: Robustness — `0.8.0` *(PR-A: pagination + isolation test)*" subsection under `[Unreleased]`: paginated list endpoints + envelope, count endpoint, client `useInfiniteQuery` + "Load more", the cross-owner isolation pytest; tests (pytest +N, vitest +N).

- [ ] **Step 4: Commit**

```bash
git add docs/DECISIONS.md docs/PLAN.md CHANGELOG.md
git commit -m "docs(phase-6): PR-A pagination + isolation — DECISIONS/PLAN/CHANGELOG"
```

---

### Task 10: Review, verify, PR

- [ ] **Step 1: Re-run both gates** (Task 5 + Task 8) — confirm green.
- [ ] **Step 2: `/code-review`** the branch diff; fix real findings.
- [ ] **Step 3: `/security-review`**; fix real findings. (Surface: the isolation test *is* the security check; pagination params are bounded by `Query`; no new mutation surface.)
- [ ] **Step 4: Live verify (owner):** a workspace with >24 generations shows a page + "Load more" that appends then disappears; Assets the same; History filters reset paging; the dashboard count is correct.
- [ ] **Step 5: Owner commit/push approval**, then push `feat/6-pagination` and open a PR into `dev` (REST API + keychain token; no `gh`).

---

## Self-Review

**Spec coverage:** limit+offset + Load more (Tasks 2,3,6,7) ✓; envelope `{items, next_offset}` (Tasks 1,3) ✓; `limit+1` sentinel, no count on hot path (Task 2) ✓; max-100 clamp (Task 3, `Query(le=100)`) ✓; defaults 24/30 (Tasks 2,3) ✓; client `useInfiniteQuery` + "Load more" (Tasks 6,7) ✓; HTTP cross-owner isolation test on assets/generations/templates + workspace (Task 4) ✓; dashboard count (Tasks 2,3,6,7 — the spec's "verify other consumers compile") ✓; tests pytest + vitest (throughout) ✓; docs (Task 9) ✓.

**Placeholder scan:** none — every code step is concrete; doc steps describe specific edits mirroring existing entries.

**Type consistency:** `GenerationPage{items,next_offset}` / `AssetPage{items,next_offset}` / `GenerationCount{count}` identical across server models (Task 1), services returning `(items, next_offset)` tuples (Task 2), routes (Task 3), client types (Task 6). `list_generations(..., *, limit, offset)` / `list_assets(..., *, limit, offset)` signatures match call sites (Tasks 2,3). `count_generations` matches route + client `useGenerationCount` (Tasks 2,3,6). `flattenPages` shape matches the infinite-query `data.pages[].items` used in Tasks 6,7. The `/count` route is declared before `/{generation_id}` (Task 3) so it isn't captured by the id param.
