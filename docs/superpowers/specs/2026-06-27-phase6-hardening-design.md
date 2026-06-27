# Phase 6 PR-B — Ingestion safety + generation concurrency + demo-guard (design)

## Context

Phase 6 PR-A bounded the list endpoints and added the HTTP isolation test. PR-B is the **final**
pre-deploy hardening slice — it closes the remaining safety/UX gaps the audit flagged so the app
holds up under real, repeated use:

1. **Ingestion has no bounds.** `ingest_asset` calls `load_sections` **synchronously inside the
   async background task** (blocking the event loop), with no parse timeout and no chunk-count cap
   beyond the PDF page cap. A pathological upload can hang ingestion or bloat the vector store, and a
   failed ingest leaves an asset stuck in `error` with no way to retry but delete + re-upload.
2. **Generation streams aren't switch-safe.** Each `use*Generation` hook aborts the *previous*
   stream on a new generate, but **not when the workspace changes mid-stream** — stale stream state
   can land in the new workspace's view. There's also no stream-inactivity timeout, the SSE
   `onError` forwards an untyped `payload.error`, and the Generate button stays enabled while
   streaming.
3. **Demo-guard inconsistency.** The card-image upload (`routes/images.py` `upload_image`) is **not**
   demo-guarded, although the Assets UI tells demo users uploads are off — server and UI disagree.

This is **PR-B of Phase 6** (PR-A = pagination + isolation). After it, Phases 0–6 are complete.

## Decisions (owner-confirmed)

- **Chunk-count overflow → reject with a clear error** (not silent truncation): completeness matters
  for a brand corpus, so tell the user to split the file rather than quietly dropping content.
- One PR covering all three tracks (they're small and independent).
- Named constants: `PARSE_TIMEOUT_S = 30`, `MAX_CHUNKS = 400`, `STREAM_INACTIVITY_MS = 30000`.

## Architecture

Three surgical tracks, no new collections, no change to the prompt/model or retrieval seams.

### A. Ingestion safety (`services/ingestion_service.py`, `routes/assets.py`)
- **Non-blocking, bounded parse:** replace the direct `load_sections(path, ct)` call with
  `await asyncio.wait_for(asyncio.to_thread(load_sections, path, content_type), PARSE_TIMEOUT_S)`.
  On `asyncio.TimeoutError` → `asset_service.mark_error(db, oid, "Parsing timed out — try a smaller
  or simpler file.")` and return. (This both bounds parse time and stops the sync parser from
  blocking the event loop.)
- **Chunk cap:** after `build_chunks`, if `len(chunks) > MAX_CHUNKS` →
  `mark_error("Document too large (N sections > 400) — split it into smaller files.")` and return
  (nothing upserted).
- **Retry / reingest:** `POST /workspaces/{id}/assets/{asset_id}/reingest` — `get_workspace_or_404`
  + `require_not_demo`; load the asset (404 if missing); **drop any existing vectors first**
  (`get_vector_store().delete_asset(namespace, asset_id)`, a no-op for an errored asset that never
  upserted) so a re-parse yielding fewer chunks can't orphan old ones; reset it to `processing`
  (clear `error`, via a new `asset_service.mark_processing`, also resetting `chunk_count`/
  `ready_chunk_count` bookkeeping); enqueue `ingest_asset` as a BackgroundTask; return the updated
  `AssetResponse` (202). Upserts are keyed `asset_id:index`, so a repeat is idempotent.

### B. Generation concurrency / state (client: `lib/sse.ts`, the `use*Generation` hooks, `GeneratePage`, `DashboardPage`)
- **Abort on workspace switch:** each `use*Generation` hook adds
  `useEffect(() => () => abortRef.current?.abort(), [workspaceId])` plus a reset to the `idle`
  initial state when `workspaceId` changes, so a switch mid-stream cancels the request and clears
  stale copy/fields.
- **Disable Generate while streaming:** `GeneratePage` disables the generate control when the active
  hook's `status === "streaming"` (the hooks already expose `status`).
- **Stream inactivity timeout:** in `readFrames`, race each `reader.read()` against a
  `STREAM_INACTIVITY_MS` timer; on expiry, `reader.cancel()` and `onError("The stream stalled — try
  again.")`. Resets on every received chunk.
- **Type-guarded `onError`:** forward `payload.error` only when `typeof payload.error === "string"`,
  else a generic "Generation failed."
- **Dashboard error state:** when `useActiveWorkspace` reports `isError`, render a small error banner
  instead of zeroed stat cards.

### C. Demo-guard reconcile (`routes/images.py`)
- Add `require_not_demo` to `upload_image` (the workspace-scoped card-image upload), matching the
  asset/workspace/logo mutation guards and the UI's claim.

## Components / files

- `server/app/services/ingestion_service.py` — constants + `asyncio.to_thread`/`wait_for` + cap.
- `server/app/services/asset_service.py` — `mark_processing(db, asset_oid)` (reset to processing,
  clear error).
- `server/app/routes/assets.py` — `POST /{asset_id}/reingest`.
- `server/app/routes/images.py` — `require_not_demo` on `upload_image`.
- `client/src/lib/sse.ts` — inactivity timeout in `readFrames`; type-guarded `onError`.
- `client/src/features/generate/use{Text,Card,PostPack,Document}Generation.ts` — abort/reset on
  `workspaceId` change.
- `client/src/features/generate/GeneratePage.tsx` — disable generate while streaming.
- `client/src/features/assets/AssetsPage.tsx` — "Retry" on errored rows (calls a new
  `useReingestAsset`); `client/src/api/assets.ts` — `useReingestAsset`.
- `client/src/features/dashboard/DashboardPage.tsx` — error banner.

## Error handling

- Parse timeout / oversized doc → asset `error` with a friendly, actionable message + Retry.
- Reingest of a missing asset → 404; by a demo user → 403.
- Stream stall/abort → `status: error` (or silent on a deliberate switch-abort), never a stuck
  spinner.
- Demo card-image upload → 403 (server), already disabled in the UI.

## Testing

- **pytest:** chunk-cap overflow → asset `error`, vector store **not** upserted (fake store asserts
  zero upserts); parse timeout → `error` (monkeypatch `load_sections` to sleep > timeout, shrink the
  constant); `reingest` flips `error`→`processing` and schedules the task, and is **403 for demo**;
  `upload_image` is **403 for demo**.
- **vitest:** `readFrames` fires `onError` after inactivity (a fake reader that never resolves);
  a `use*Generation` hook aborts + resets when `workspaceId` changes; `onError` ignores a non-string
  `payload.error`.

## Out of scope

- Card presets (Phase 5 PR-B — owner leaning cut); the `dev → main` release/tag pass; the second
  demo brand; any change to retrieval, prompts, or the model path.

## Verification

Stack: `docker-compose up` + server + `npm run dev`. Live: upload a huge/garbage file → the asset
shows a friendly error + Retry; Retry re-runs ingestion; start a generation then switch workspace →
the stream cancels and the new workspace shows a clean Generate page; the Generate button is disabled
while streaming; as the demo user, card-image upload is blocked. Per-PR gate: server ruff + mypy +
pytest; client tsc + eslint + prettier + build + vitest; then `/code-review` + `/security-review`,
owner commit/push approval, PR into `dev`.
