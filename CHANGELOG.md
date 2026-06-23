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

_Next: `0.1.0` — Phase 1a (LinkedIn text posts, the RAG loop). Not started._

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
