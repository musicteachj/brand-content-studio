# Changelog

All notable changes to Brand Content Studio are recorded here, newest first.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning is `0.MINOR.PATCH`
mapped to build phases (see [`docs/PLAN.md`](./docs/PLAN.md)); `1.0.0` is reserved for the first public deploy:

| Version | Phase |
|---|---|
| `0.0.0` | Phase 0 — scaffold |
| `0.1.0` | Phase 1a — text posts (the RAG loop) |
| `0.2.0` | Phase 1b — image cards |
| `0.3.0` | Phase 1.5 — customization |
| `0.4.0` | Phase 2 — document output |
| `1.0.0` | first public deploy |

Git tags (`v0.0.0`, …) are created when a phase merges to `main` (see [`docs/WORKFLOW.md`](./docs/WORKFLOW.md) §7).

## [Unreleased]

### Added — Phase 1a: LinkedIn text posts (the RAG loop) — `0.1.0`

The full RAG loop end-to-end: upload brand assets → ingest → hybrid retrieval → stream an on-brand LinkedIn post → inspect what was retrieved → save to history. Implements Phase 1a of [`docs/PLAN.md`](./docs/PLAN.md).

- **Models + workspace CRUD** — Pydantic v2 models (`workspace`/`asset`/`generation`/`common`), `routes/workspaces.py` CRUD + `workspace_service`, `get_workspace_or_404` ownership dependency, and an `is_demo` guard (`require_not_demo`) that disables destructive actions so visitors can't break the seeded corpus.
- **Storage + ingestion** — `StorageBackend` protocol + local FS impl (path-traversal-guarded, server-derived keys); `routes/assets.py` upload (202 + `BackgroundTask`) / list / get / delete with type + 10 MB size validation; `ingestion_service` pipeline (parse → chunk → embed → upsert → mark ready) with `pdfplumber` (page-aware) + markdown loaders, `RecursiveCharacterTextSplitter` (800/120), and one-chunk-per-post splitting for exemplar posts.
- **Hybrid retrieval + generation** — `retrieval_service` always injects the brand fundamentals (voice + pillars) then adds semantic top-k, fully workspace-scoped; `prompts/text_post.py` wraps retrieved chunks in a delimited `<brand_context>` block framed as data-not-instructions (prompt-injection defense); `generation_service` streams Claude (`claude-sonnet-4-6`, mirrors EMS); `POST /generate/text` SSE emits `{text}` deltas → terminal `{meta}` (retrieval debug payload + generation id) → `[DONE]`, blocking generation on an empty corpus before Claude is called.
- **History** — generations persisted server-side at stream end with a retrieval snapshot (survives later asset deletes); `routes/generations.py` list (type filter) / get / delete.
- **Client** — `lib/sse.ts` (fetch + `ReadableStream`, POST + JWT); Asset Manager (upload + ingestion status pills with live polling), Generate page (Controls + streamed post output with `aria-live` + Retrieval Debug Panel), Content History grid + detail dialog, Workspace Setup stepper, real dashboard stats. Built on the Folio design system (token-driven, no hardcoded hex, a11y states).
- **RAG pytest backbone** — deterministic fake embedder/vector store; tests for chunking size/overlap, **workspace-scoped query isolation** (no cross-leak), top-k scores, hybrid always-injects voice **and** pillars, empty-corpus block (Claude not called), SSE persists `retrieved_chunk_ids`, plus an **eval harness** (8 briefs → expected chunks, hit-rate threshold). 18 tests.
- **Seed** — the rich Verdure corpus (voice PDF + pillars/posts/personas/competitors markdown) ingested into the Verdure workspace; idempotent.

### Fixed
- **Code-review findings (high)** — deterministic pinned-chunk ordering (was Python-set iteration); corpus-ready gate no longer reads a stale workspaces cache after ingest; empty model completions are no longer persisted as `complete`; asset doc + counters are written only after the file is stored (no orphan/counter drift on a storage failure); orphan vectors are dropped if an asset is deleted mid-ingest; CRLF-tolerant SSE frame parsing; the retrieval debug panel no longer uses the reserved action accent for score bars (DESIGN §7) and omits unpersisted latency/k when re-opened from history; seed `asset_count` is derived from actually-ingested files.
- **Content pillars now always pinned** — raised the pinned-fundamentals fetch limit so a multi-chunk voice guide can't crowd pillars out of retrieval (DECISIONS #16). _(Found by the live acceptance run.)_
- **Dev tooling** — `dev:server` + `seed` run via the server virtualenv (`.venv/bin/python`) so Phase 1a's RAG deps resolve; root deps installed so `npm run dev` (`concurrently`) works.

### Verified
- **Quality gates** — server `ruff` + `mypy` + `pytest` (18) green; client `tsc` + `eslint` + `prettier` + production build green.
- **Live acceptance (real OpenAI + Chroma + Claude + Mongo)** — seeded the Verdure corpus (32 chunks across 5 assets, incl. the voice PDF via `pdfplumber`); two distinct briefs streamed on-brand posts grounded in the corpus, retrieved **different** chunks, surfaced ≥3 sources in the debug panel, and persisted to history; confirmed hands-on in the UI.
- **Review gate (Tier-2)** — `/code-review` (high): 8 findings fixed (above); `/security-review` (full): clean; plus a focused follow-up security pass over the post-review changes: clean.

### Notes
- Asset upload/delete is disabled for the seeded demo user (`is_demo` guard); generation is allowed. Exercising the upload pipeline through the UI requires a non-demo account (no public signup).
- Generation uses `claude-sonnet-4-6`; retrieval embeddings use OpenAI `text-embedding-3-small` (1536-dim). Both API keys live only in the gitignored `server/.env`.

---

## [0.0.0] — Phase 0: Scaffold — 2026-06-22

First runnable scaffold: monorepo + FastAPI backend + RAG vector-store seam + React/Vite/Tailwind client shell. Implements Phase 0 of [`docs/PLAN.md`](./docs/PLAN.md). Deployment is deferred (local-first).

### Added
- **Monorepo** — root npm scripts (`dev`/`build`/`seed` via `concurrently`), `docker-compose.yml` (mongo:7 + chromadb/chroma), multi-stage `Dockerfile`, `.gitignore`.
- **Backend (FastAPI + Motor + Pydantic v2)** — `config`, MongoDB connection + index ensure, lifespan app, `GET /api/health` (reports mongo + vector_store).
- **Auth** — JWT (python-jose + bcrypt), `get_current_user` dependency, `POST /auth/login`, `GET /auth/me`, and the `POST /auth/demo-login` "Explore as demo" bypass for the seeded demo user. No public signup.
- **RAG seam** — `VectorStore` protocol + factory, OpenAI `Embedder` (built lazily), `ChromaStore` (one collection per workspace), `QdrantStore` deferred stub.
- **Seed** — `seed_demo.py` creates the demo user + an empty "Verdure Materials" workspace (idempotent).
- **Client (React 19 + Vite + TS + Tailwind)** — Folio design tokens (HSL CSS vars), shadcn-style `Button`/`Input`, light-first theme toggle, **Login** ("Explore as demo" + password), **AppShell** + collapsible **SideNav**, **Dashboard**, protected routing, persisted Zustand auth + axios interceptor. Built with the Claude design skills (`frontend-design`).
- **Tooling** — eslint + prettier; client typecheck/lint/format/build quality gate.

### Fixed
- Demo/login flow no longer persists a half-authenticated state (`isAuthenticated=true` with a null user) if `/auth/me` fails after the token is issued — the session now rolls back on failure. _(Found by the Phase 0 code review.)_

### Verified
- **Client** — typecheck + lint + prettier + production build all green.
- **Backend** — boots cleanly; `GET /api/health` → `{mongo:true, vector_store:true}`; `demo-login` returns a JWT through the Vite proxy; `/auth/me` returns the demo user.
- **Review gate (Tier-2)** — `/security-review` clean; `/code-review` (high) surfaced one low-severity issue, fixed above.

### Notes
- Deployment (AWS shared platform via CDK) is a later phase; dev runs entirely local (Docker mongo + chroma).
- The default JWT secret must be overridden in production and the app should fail closed if it isn't — tracked for the deploy phase.
