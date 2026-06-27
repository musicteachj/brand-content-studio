# Phase 6 PR-A — Pagination + cross-workspace isolation test (design)

## Context

Phase 6 is the pre-deploy hardening round. Two real gaps exist **today**, and the demo seed +
multi-brand work has only made them more reachable:

1. **Unbounded lists.** `GET …/generations` and `GET …/assets` return *every* row
   (`asset_service.list_assets`, `generations_service.list_generations` — a bare `find().sort()`
   with no limit). History and Assets grow without bound; a heavy workspace ships the whole list on
   every load.
2. **No HTTP-level tenancy test.** Cross-workspace isolation is only proven at the *retrieval* unit
   layer (`test_query_is_workspace_scoped`). `get_workspace_or_404` enforces ownership on every
   workspace-scoped route, but nothing asserts end-to-end that owner A's token can't read owner B's
   data — exactly the guarantee that matters most as the app goes multi-brand.

This is **PR-A of Phase 6**. PR-B (ingestion caps + generation concurrency/state + demo-guard
reconcile) is a separate follow-up spec.

## Decisions (owner-confirmed)

- **Limit + offset, "Load more"** (not cursor/numbered pages) — simplest correct fit at this scale.
- List endpoints return a small **envelope** `{ items, next_offset }` (`next_offset: null` when
  exhausted) instead of a bare array — so the client knows when to stop.
- **2-PR split**, this is PR-A.

## Architecture

A focused, read-only change to the two list endpoints + their clients, plus one new pytest.

**Server:** the two list services gain `limit` + `offset`. To compute `next_offset` without a
`count()`, fetch **`limit + 1`** rows: if the extra row exists there's another page
(`next_offset = offset + limit`), else `next_offset = None`; return the first `limit` items. Routes
accept `?limit&offset`, clamp `limit` to `[1, 100]` (default 24 generations / 30 assets) and `offset`
to `>= 0`, and return the envelope. Type filter on generations is unchanged (applies before paging).

**Client:** both lists move to `useInfiniteQuery` (react-query), keyed by workspace (+ filter for
generations), `getNextPageParam` reading `next_offset`. History and Assets render the flattened
`items` and a **"Load more"** button shown while `hasNextPage`. Changing the History filter starts a
fresh infinite query (filter is in the query key).

**Isolation test:** a pytest that creates two workspaces under **different owners** and asserts owner
A's token receives **404** on B's workspace-scoped routes.

## Components

**Server**
- `models/generation.py` — add `GenerationPage { items: list[GenerationResponse]; next_offset: int | None }`.
- `models/asset.py` — add `AssetPage { items: list[AssetResponse]; next_offset: int | None }`.
- `services/generations_service.list_generations(db, workspace_oid, type_filter, *, limit, offset)` →
  `(items, next_offset)`; uses the `limit + 1` sentinel + `.skip(offset).limit(limit + 1)`.
- `services/asset_service.list_assets(db, workspace_oid, *, limit, offset)` → same shape.
- `routes/generations.py` `list_generations` and `routes/assets.py` `list_assets` — add
  `limit: int = Query(24|30, ge=1, le=100)`, `offset: int = Query(0, ge=0)`, return the page model.
- A shared clamp isn't needed (FastAPI `Query(ge=, le=)` enforces bounds).

**Client**
- `api/generations.ts` `useGenerations` → `useInfiniteQuery`; response type `GenerationPage`
  (`{ items: Generation[]; next_offset: number | null }`). Expose a flattened `generations` +
  `fetchNextPage`/`hasNextPage`/`isFetchingNextPage` (or return the query and let the page flatten).
- `api/assets.ts` `useAssets` → `useInfiniteQuery` with `AssetPage`.
- `features/history/HistoryPage.tsx` + `features/assets/AssetsPage.tsx` — flatten `data.pages`,
  render a "Load more" button gated on `hasNextPage`. Keep existing empty/loading/error states.
- `types/index.ts` — `GenerationPage`, `AssetPage` envelope types.
- Verify other consumers of `useAssets`/`useGenerations` (e.g. any dashboard count) still compile;
  update call sites in lockstep. The corpus-ready gate reads `ready_chunk_count` off the workspace,
  **not** the assets list, so it's unaffected.

## Data flow

`GET /workspaces/{id}/generations?type=card&limit=24&offset=0` → `{ items:[…24], next_offset:24 }`
→ client renders, shows "Load more" → `…&offset=24` → `{ items:[…N<24], next_offset:null }` →
button hides. Identical shape for assets.

## Error handling

- `limit`/`offset` out of range → FastAPI 422 (bounded by `Query`).
- Ownership/existence unchanged — `get_workspace_or_404` still 404s a non-owner before any list runs.
- Empty page → `{ items: [], next_offset: null }`; client shows the existing empty state.

## Testing

- **pytest (pagination):** seed N>limit generations (and assets); first page returns `limit` items +
  a non-null `next_offset`; second page returns the remainder + `next_offset: null`; `limit` above
  100 → 422; the generations type filter still applies under paging.
- **pytest (HTTP isolation):** create workspace A (owner A) and workspace B (owner B); with A's
  identity, `GET` B's `/assets`, `/generations`, `/templates`, and the workspace itself all return
  **404** (never B's data); a sanity check that A *can* read its own. This is the end-to-end
  complement to `test_query_is_workspace_scoped`.
- **vitest:** History/Assets render the flattened pages and show "Load more" only when
  `next_offset` is set; clicking it requests the next offset (mock the api).

## Out of scope (PR-B / later)

- Ingestion caps + retry, generation concurrency/state, demo-guard reconcile — **PR-B**.
- Cursor pagination, numbered pages, server-side search/sort options.
- Paginating the templates list (already tiny — capped per workspace).

## Verification

Stack: `docker-compose up` + server + `npm run dev`. Live: with a workspace that has >24
generations, History shows a page + "Load more" that appends the next page and then disappears; same
for Assets; filters reset paging. Per-PR gate: server ruff + mypy + pytest; client tsc + eslint +
prettier + build + vitest; then `/code-review` + `/security-review`, owner commit/push approval, PR
into `dev`.
