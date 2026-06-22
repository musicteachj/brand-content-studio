# Build Plan — Phased Roadmap

> The execution roadmap for Brand Content Studio (**what** to build, in what order). Decisions follow [DECISIONS.md](./DECISIONS.md); technical detail lives in [ARCHITECTURE.md](./ARCHITECTURE.md) and [DATA_MODEL.md](./DATA_MODEL.md); **how** we build it — vertical slices, front/back ordering, branching, commits — is in [WORKFLOW.md](./WORKFLOW.md).
> **Status: planning complete, code not yet started.** This document is the build reference.

Build order: **Phase 0 scaffold → 1a text posts → 1b image cards → 1.5 customization → 2 documents → deferred AWS deployment.** Each phase lists concrete steps, the files it touches, an acceptance criterion, and how to verify.

---

## Phase 0 — Scaffold

**Goal:** both apps run locally and talk to each other; the RAG seam exists but is empty.

Steps:
1. Root `package.json` (copy EMS `dev` / `dev:client` / `dev:server` / `build` + `concurrently`); `docker-compose.yml` adds `mongo:7` + `chromadb/chroma`.
2. `client/`: Vite + React + TS; install Tailwind, shadcn/ui (`components.json`), Zustand, react-query, react-hook-form, zod, lucide-react. Paste Folio tokens into `tailwind.config.ts` + `index.css` (`:root`/`.dark` CSS vars from DESIGN §1). Build `AppShell` + `SideNav`.
3. `server/`: copy EMS `config.py`, `database.py`, `main.py`, `utils/{security,dependencies}.py`, `auth_service.py`, `models/user.py`, `routes/{health,auth}.py`. Rename DB to `brand_content`. Extend config: `openai_api_key`, `vector_store_backend="chroma"`, chroma path/url, `qdrant_url`, `unsplash_access_key`, `storage_backend="local"`, `s3_bucket`, `embedding_model`, `embedding_dim=1536`.
4. `app/rag/`: define `VectorStore` Protocol, `Embedder` Protocol + `OpenAIEmbedder`, `ChromaStore`, factory `get_vector_store()`. Init the store in `main.py` lifespan; ensure Mongo indexes in lifespan.
5. `seed/seed_demo.py`: create the demo user (`is_demo`) + an empty Verdure workspace. Add `POST /auth/demo-login` (logs into the seeded demo) and an `is_demo` guard that blocks destructive actions (delete workspace, delete/re-ingest assets) so visitors can't break the seed.

**Files:** root `package.json`, `docker-compose.yml`, `client/tailwind.config.ts`, `client/src/index.css`, `server/app/{config,database,main}.py`, `server/app/rag/*`, `server/app/utils/*`, `server/seed/seed_demo.py`.

**Acceptance:** `npm run dev` starts both. `GET /api/health` returns mongo + vector_store healthy. Demo login returns a JWT and loads the empty workspace shell. Dark mode works; no hardcoded hex in components.

---

## Phase 1a — LinkedIn text posts (the RAG loop)

**Goal:** upload brand assets → retrieve → stream an on-brand text post → see what was retrieved.

Steps:
1. `models/{workspace,asset,generation}.py`; `routes/workspaces.py` CRUD; `services/workspace_service.py`.
2. `services/storage_service.py` (Local FS); `routes/assets.py` upload + list/status; `services/asset_service.py` + `ingestion_service.py` (loaders → chunk → embed → upsert → mark ready) as a `BackgroundTask`.
3. `services/retrieval_service.py` (**hybrid** — always include `voice_summary` + pillars, then semantic top-k); `prompts/text_post.py` (retrieved chunks wrapped in a delimited `<brand_context>` block, treated as data not instructions); `services/generation_service.py` (streaming, mirror EMS `ai_service.py`); `routes/generate.py` `/generate/text` SSE.
4. `routes/generations.py` persist + history list/get.
5. Client: `workspace-setup` stepper (name + asset upload), `assets` manager with ingestion pills, `generate` ControlsPanel + streamed text output via `lib/sse.ts`, `RetrievalDebugPanel`, basic `history` grid. Empty-corpus state: block generation with an "ingest assets first" message when no ready chunks.
6. Seed the **rich Verdure corpus** (see [demo-corpus/](./demo-corpus/)) and ingest it.
7. **RAG eval harness:** a small fixture set (8–10 briefs → expected-to-retrieve chunk ids) measuring retrieval hit-rate, so chunking / k / hybrid weighting can be tuned against a number.

**Files:** all of `app/rag` exercised, `app/services/*`, `routes/{workspaces,assets,generate,generations}.py`, client `features/{workspace-setup,assets,generate,history}`.

**Acceptance:** Upload a PDF → pill goes processing→ready with `chunk_count > 0`. Enter a brief → tokens stream into the UI → debug panel shows ≥3 Verdure chunks with scores → output is recognizably on-brand → it appears in history with `retrieved_chunk_ids`. Two different briefs retrieve different chunks (proves retrieval, not just generation).

---

## Phase 1b — Image cards + PNG export (the design system)

**Goal:** generate a designed 1080×1350 card in the workspace's brand and export it.

Steps:
1. `prompts/image_card.py`; extend `generation_service` / `routes/generate.py` with `/generate/card` SSE (stream natural text for the typing effect; final structured fields via Anthropic **tool-use**; `suggested_keywords`).
2. `services/unsplash_service.py` + `routes/images.py` (search proxy + upload); attribution normalization + download-tracking.
3. Client `features/generate/cards/` three archetypes (PhotoLed, Statement, Quote) authored in **Satori's CSS subset**, `CardPreview` (workspace fonts/colors, 1080×1350; same Satori definition for final preview + export), `ImagePickerPanel` (slide-in), brand-font **buffer** loader, `useCardExport` (Satori → `@resvg/resvg-wasm` → PNG).
4. Template picker (explicit selection, no auto-select) in ControlsPanel.
5. Persist card generations; history thumbnails render the card.

**Files:** `prompts/image_card.py`, `routes/images.py`, `services/unsplash_service.py`, client `features/generate/cards/*`, `CardPreview.tsx`, `ImagePickerPanel.tsx`, `useCardExport.ts`.

**Acceptance:** Pick a template → copy streams live into the card → keywords populate Unsplash search → pick an image → attribution renders automatically → export a crisp 1080×1350 PNG → the card uses Verdure forest-green/serif, never Folio magenta/Jakarta. Uploaded-image path also works.

---

## Phase 1.5 — Customization

Layout swap (re-render same copy in a different archetype), image swap without regenerating copy (replace `image` only), inline text editing in the preview (`PATCH` generation `output.fields`), accent color toggle within the brand palette.

**Files:** `CardPreview` (editable fields), `routes/generations.py` PATCH, `stores/useGenerateStore`.

**Acceptance:** Edit a headline in-preview and re-export without re-calling Claude (client makes no `/generate` request); swap image and template without losing copy; changes persist on save.

---

## Phase 2 — Document output

Branded `.docx` (python-docx), `.pptx` (python-pptx), and PDF (preserves formatting). New `routes/documents.py` + `services/document_service.py` reusing the retrieval step. Add the deps to `requirements.txt`.

**Acceptance:** Generate a branded one-pager `.docx` and matching PDF from a brief, downloaded with workspace colors/fonts applied.

---

## Deployment phase (deferred) — AWS shared platform via CDK

Per `./aws_infrastructure_plan.md` Phase 3. CDK app: ECS Fargate service (FastAPI behind ALB), S3 + CloudFront for the SPA, shared Qdrant collection `brand-content-studio`, shared Mongo database `brand_content`, Secrets Manager `brand-content-studio/*`. Flip `vector_store_backend=qdrant`, `storage_backend=s3`. Tag every resource `project: brand-content-studio`, `env: production`.

**Acceptance:** the same demo flow works against Qdrant + S3; embedding dim 1536 stays consistent so seeded vectors are queryable.

---

## Verification strategy

Run `docker-compose up` + `npm run dev` for every phase. Every phase also passes the **quality gate**: `ruff` + `mypy` (server), `eslint` + `prettier` + `tsc --noEmit` (client) — wired into CI in the deploy phase (see [WORKFLOW.md](./WORKFLOW.md) §5).

- **Phase 0:** `curl /api/health`; `python -m seed.seed_demo`; click "Explore as demo". pytest: `test_health`, `test_demo_login_returns_jwt`, `test_vector_store_factory_returns_chroma`.
- **Phase 1a (pytest is the backbone of RAG confidence):**
  - `test_chunking_respects_size_overlap` (deterministic fixture).
  - `test_ingestion_marks_ready_and_counts_chunks` (small fixture PDF).
  - `test_query_is_workspace_scoped` — ingest two workspaces, query one, assert no cross-leak (the isolation test).
  - `test_retrieval_returns_topk_with_scores`.
  - `test_hybrid_retrieval_always_includes_voice` — voice/pillars present even when not the top semantic match.
  - `test_empty_corpus_blocks_generation` — no ready chunks → generation blocked, Claude not called.
  - **Eval harness** — run the 8–10-brief fixture set, assert retrieval hit-rate ≥ a threshold (tune chunking/k against it).
  - `test_generate_text_persists_retrieved_chunk_ids` (mock Anthropic stream; assert SSE frames `{text}…{meta}…[DONE]` + a persisted generation).
  - Use a fake/deterministic embedder in unit tests (no network/cost); one optional integration test hits real OpenAI behind an env flag.
  - Manual: upload PDF, watch the pill flip, run two distinct briefs, inspect debug-panel scores.
- **Phase 1b:** Vitest component tests — `CardPreview` renders workspace fonts not app fonts (assert computed `font-family`); attribution renders when `image.attribution` present. pytest: `test_unsplash_search_normalizes_attribution` (mock httpx). Manual: export the PNG, open it, verify 1080×1350 + brand fidelity.
- **Phase 1.5:** test `PATCH` updates `output.fields`; re-export makes no `/generate` call.
- **Phase 2:** open generated `.docx`/`.pptx`/PDF; python-docx style assertions confirm branded styles.
