# Architecture

> Reconciled technical architecture for Brand Content Studio. Decisions here follow [DECISIONS.md](./DECISIONS.md) (source of truth).
> Related: [PLAN.md](./PLAN.md) · [DATA_MODEL.md](./DATA_MODEL.md) · [DESIGN.md](./DESIGN.md) · [aws_infrastructure_plan.md](./aws_infrastructure_plan.md)

---

## 1. Stack at a glance

| Layer | Choice | Mirrors |
|---|---|---|
| Frontend | React 19 + Vite 8 + TS, Tailwind 4 + shadcn/ui (Radix), Zustand, TanStack Query, react-hook-form + zod, lucide-react; Node 24 | Smart Resume Builder |
| Backend | Python 3.12, FastAPI (Starlette 1.x) + Motor (async MongoDB) + Pydantic v2 | Employee Management System |
| Generation | Claude `claude-sonnet-5-5` via `AsyncAnthropic`, streamed over SSE (DECISIONS #40) | EMS `ai_service.py` |
| Embeddings | OpenAI `text-embedding-3-small` (1536-dim) behind `Embedder` protocol | new |
| Vector store | Chroma, in-process (`chromadb.PersistentClient`, no server), behind the `VectorStore` protocol | new |
| RAG orchestration | Hand-rolled (SDKs + vector-store client directly); `langchain-text-splitters` (standalone) for chunking; pdfplumber | new |
| App DB | MongoDB (Docker dev / MongoDB Atlas M0 in production, DECISIONS #46) | EMS |
| Auth | PyJWT (HS256, algorithms pinned); visitors start a private 24-hour demo session behind a Turnstile check; password login is development only | EMS |
| Images | Unsplash API (server-proxied) + user upload | new |
| Storage | Local FS behind `StorageBackend` protocol (the only implemented backend); production uses the retained data volume, `get_storage()` supports `local` only | new |
| Card export | Satori (HTML/JSX→SVG) + `@resvg/resvg-wasm` (SVG→PNG) → 1080×1350 PNG; client-side, free; no server-side fallback | new |

**Local dev is fully decoupled from the cloud.** `docker compose up -d` brings up `mongo:7` only (Chroma runs in-process in the API server); `npm run dev` runs client + server. No AWS needed until the deferred deployment phase.

---

## 2. Repo structure (monorepo)

Root `package.json` runs both apps via `concurrently`; multi-stage `Dockerfile` builds the SPA with Node, then Python serves `client/dist` (`app/spa.py`, `mount_spa`: real files as files, hashed `/assets/*` cached as immutable, every other path gets `index.html`, unknown `/api/...` paths are a JSON 404). `docker-compose.yml` provides `mongo:7`; `docker-compose.prod.yml` (project `folio-local`) runs the production image locally the way production runs it (see [DEPLOY.md](./DEPLOY.md)).

```
server/app/
  config.py database.py main.py limits.py   # limits.py: every upload/size/count cap in one place; lifespan: connect Mongo + init vector store + ensure indexes; pure-ASGI security-headers middleware (incl. the CSP, `csp_mode`; DECISIONS #36)
  spa.py                                 # production only: serve the built client (mount_spa)
  routes/    auth · status · examples · workspaces · assets · templates · generate · documents · generations · images · health
  services/  auth · workspace · asset · ingestion · retrieval · ai (Claude client) · generations (Mongo persistence) ·
             document · template · content_extraction · brand_extract · brand_fonts · upload · unsplash · storage · session (visitor demo sessions) · turnstile (bot check) · ai_ledger · ai_meter · ai_pricing · ai_failures · ai_clients · claude_calls (the dollar ledger and every model call, see section 5a)
  rag/       vector_store(Protocol + factory) · chroma_store · embeddings · chunking · loaders
  models/    common · user · workspace · asset · generation · template · image
  prompts/   text_post · image_card · post_pack · document · template_fill · brand_extract · exemplars · context
  jobs/      cleanup (python -m app.jobs.cleanup, the hourly scheduled task)
  utils/     security · dependencies (get_current_user, get_workspace_or_404, …) · sse · errors · ratelimit · archives
  assets/fonts/                          # brand TTFs used when rendering PDFs

server/seed/                             # outside app/: seed_demo.py (the self-healing ensure_demo_seed) + verdure_corpus/ (a copy of docs/demo-corpus/ plus voice-and-tone.pdf) + fixtures/ (verdure_embeddings.json, examples.json)

client/src/
  lib/       api.ts · sse.ts (fetch + ReadableStream; NOT EventSource) · apiError.ts · utils.ts (cn) · theme · colorTint · useRovingRadio
  components/ ui/ (shadcn) · layout/ (AppShell, SideNav, TopBar, ThemeToggle, WorkspaceSwitcher) · Brand · DemoNotice · ConfirmDialog
  features/  auth · workspace-setup · workspace · dashboard · generate · history · assets · templates · settings
             # generate/ = the 4 streamed-generation hooks + CardPreview · cards/ · ImagePickerPanel · RetrievalDebugPanel
  stores/ (auth, workspace, generate, settings) · api/ · types/ · styles/ (brand-font injector) · test/ (factories + MSW)
  App.tsx · main.tsx
```

### Reuse from sibling projects (do not reinvent)

| Need | Reuse from |
|---|---|
| SSE streaming generation | `employee-management-system/server/app/services/ai_service.py` |
| SSE frame shape (`data: {json}\n\n` + `[DONE]`) | `employee-management-system/server/app/routes/ai.py` |
| JWT / auth dependency | `employee-management-system/server/app/utils/{security,dependencies}.py` |
| Monorepo orchestration + Dockerfile | `employee-management-system/package.json` + `Dockerfile` |
| Tailwind + shadcn + Zustand frontend conventions | `smart-resume-builder/client` |

---

## 3. RAG: vector-store abstraction

`app/rag/vector_store.py` defines a `VectorStore` Protocol; `get_vector_store()` returns the impl named by `settings.vector_store_backend` (`"chroma"`).

```python
class Chunk(TypedDict):
    id: str            # "{asset_id}:{chunk_index}"
    text: str
    metadata: dict     # {workspace_id, asset_id, filename, asset_kind, chunk_index, page?}

class RetrievedChunk(TypedDict):
    id: str; text: str; score: float; metadata: dict

class VectorStore(Protocol):
    async def upsert_chunks(self, workspace_id: str, chunks: list[Chunk], embeddings: list[list[float]]) -> int: ...  # the store never embeds
    async def query(self, workspace_id: str, query: str, query_embedding: list[float], k: int = 6) -> list[RetrievedChunk]: ...
    async def get_by_kinds(self, workspace_id: str, kinds: list[str], limit: int = 8) -> list[RetrievedChunk]: ...  # pinned fundamentals
    async def count(self, workspace_id: str) -> int: ...
    async def delete_workspace(self, workspace_id: str) -> None: ...
    async def delete_asset(self, workspace_id: str, asset_id: str) -> None: ...
    async def health(self) -> bool: ...
```

- **Embedding** goes through an `Embedder` protocol (`OpenAIEmbedder`, `text-embedding-3-small`, 1536-dim), and every call is metered by the AI ledger (`embed_metered`). No service calls OpenAI directly: a provider swap touches `embeddings.py` only. The vector store itself does not embed.
- **Chroma (in-process):** `chromadb.PersistentClient` on local disk (`CHROMA_PATH`), telemetry off, never its default embedding model; there is no Chroma server (DECISIONS #44). One collection per workspace, `ws_{workspace_id}`; isolation = separate collection. One process per directory, so there is exactly one Folio task and deploys stop the old one first.
- Collections pin **1536 / cosine**.
- **The pipeline is hand-rolled, no LLM framework.** Embedding uses the OpenAI SDK; storage/retrieval use the Chroma client; generation uses the Anthropic SDK. The `VectorStore`/`Embedder` protocols are the only abstraction. Only the standalone `langchain-text-splitters` package is pulled in (for `RecursiveCharacterTextSplitter`); full LangChain is deliberately avoided.

---

## 4. RAG pipeline — ingestion

Non-blocking via FastAPI `BackgroundTasks` (the upload response returns immediately; the UI polls for the status pill). Lives in `asset_service` → `ingestion_service`.

```
upload (multipart) → validate type/size → store raw (StorageBackend) → create asset {status: processing}
  → [BackgroundTask] parse (pdfplumber / text) → chunk → embed (OpenAI, batched) → upsert_chunks
  → mark asset {status: ready, chunk_count} + bump workspace counters
  (on error → asset {status: error, error})
```

- **Chunking:** `RecursiveCharacterTextSplitter` from the standalone `langchain-text-splitters` package (no full LangChain), **chunk_size 800 / overlap 120** chars, separators `["\n\n","\n",". "," "]`. The **past-posts** asset kind is split **one chunk per post** (whole exemplar posts are the highest-value retrieval target).
- **Chunk vectors live in the vector store, not Mongo.** Mongo stores only `chunk_count` + status. Chunk text/metadata are returned by the store at query time.

---

## 5. RAG pipeline — retrieval + generation

### Text post (Phase 1a — proves the loop)
```
POST /workspaces/{id}/generate/text {brief, tone?, length?}   → text/event-stream
  retrieve (concurrently): get_by_kinds(workspace_id, ["voice","pillars"], limit=16)  +  embed(brief) → query(workspace_id, k=6)
            → pinned chunks first, then semantic hits by score, de-duplicated
  prompt: system (brand ghostwriter rules + voice_summary) + user (brief + <brand_context> tagged by source)
  stream Claude → {text} frames … terminal {meta: retrieval} … [DONE]
  persist generation {type:text, output:{post_text, hashtags, char_count}, retrieved_chunk_ids, retrieval_meta}
```

**Retrieval debug panel contract** (returned as the terminal `meta` event and stored on the generation):
```
per chunk: {chunk_id, asset_id, filename, asset_kind, score, pinned, preview(~240ch), chunk_index, page?}
envelope:  {k, retrieved[], embedding_model, latency_ms}
```
The panel (DESIGN: "precise, trustworthy tooling — no glow") lists each source with a score bar and a peek of the matched text. It is the proof the RAG loop works.

- **Hybrid retrieval:** chunks from the `voice` and `pillars` asset kinds are *always* included (`PINNED_KINDS`, up to `PINNED_LIMIT` = 16; brand fundamentals shouldn't depend on a similarity hit), and semantic top-k (k = 6, set in the generate routes) adds the most relevant posts and sections. Pinned chunks are flagged `pinned` and shown as "Pinned" in the panel. Separately, the workspace's `voice_summary` goes into the system prompt. Always workspace-scoped.
- **Prompt-injection defense:** retrieved chunks are wrapped in a clearly delimited `<brand_context>` block, and the system prompt instructs Claude to treat their contents as brand *material to emulate*, never as instructions. Ingested brand docs are untrusted input.
- **Empty/thin corpus:** if the workspace has no ready chunks, block generation with a clear "ingest assets first" state — never call Claude with no brand context.
- **RAG eval harness:** a small fixture set (8–10 briefs → expected-to-retrieve chunk ids) measures retrieval hit-rate, so retrieval quality is a number we can tune (chunk size, k, hybrid weighting), not a vibe.

### 5a. The AI dollar ledger: reserve before, settle after (DECISIONS #42)

Every paid call (Claude and OpenAI embeddings) goes through `ai_ledger`, in integer micro-dollars, with atomic conditional updates and no lock held across a model call.

```
route admitted → retrieve (embedding reserved, then settled from the reported tokens)
  → build every prompt → reserve each Claude call's worst-case cost (a visitor must be below AI_VISITOR_BUDGET_USD,
    and today's total must stay within the day's pacing allowance; refusal = plain HTTP 429/503, before any SSE frame)
  → SSE response starts → model call → settle from `usage` (shielded, so cancellation can't skip it)
```

- **Pacing (UTC):** `allowance_today = min(left_this_month, max(AI_PACING_MULTIPLIER x left_this_month / days_left_including_today, AI_DAILY_FLOOR_USD))`; the month is never exceeded. `AI_MONTHLY_BUDGET_USD=0` turns live AI off. A visitor is admitted while their counted spend (settled plus open) is below `AI_VISITOR_BUDGET_USD`; one call can go over.
- **Settling:** a response's usage is settled before a decline, a token cap, or bad JSON is raised. A failure the provider never bills (401, 402, 403, a usage-limit or low-credit 400, any 429, an overloaded error before any output) settles to $0; a timeout, dropped connection, cancellation, or unknown outcome keeps the whole reservation, and so does an overloaded error after any streamed output (thinking counts). A sweeper in the cleanup job charges reservations open longer than 10 minutes.
- **Streams:** the four Generate routes reserve before the SSE response, send a `: keep-alive` comment after each 10 s of silence, and settle the instant the client disconnects (`sse_response(..., on_close=...)` closes the route's generator and model stream, shielded; an unstarted call is released at $0).
- **Public status:** `GET /api/status` (no auth, cached 30 s) reports `live_ai_available`, a reason, the Turnstile site key, and whether password sign-in is open. Clients disable live generation and point at the examples when it is false.
- **Clients:** one shared `AsyncAnthropic` and one `AsyncOpenAI`, `max_retries=0`, explicit timeouts, server-side fallbacks off (DECISIONS #43).

### 5b. Demo sessions (DECISIONS #41)

`POST /api/auth/demo-login {turnstile_token}` verifies the token with Cloudflare (siteverify, 5 s timeout, only for this app's host and the `demo-start` action; a refusal is a 403, an outage a 503), applies per-IP start limits, creates a `demo_sessions` document, and returns a 24-hour JWT carrying its ID as `sid`. `get_current_user` accepts a visitor's token only while that session is live (otherwise 401 `demo_ended`). Every generation read and write goes through `generations_service.scope_filter`: a visitor reaches their own session's work plus the ready-made examples (`is_example`), and examples are read-only for everyone. The hourly cleanup job removes expired visitor work (files first, then records), expired sessions, and their spend totals. The demo user has an unusable password and can't sign in with one; `POST /api/auth/login` is a 404 in production.

### 5c. Startup, seed, and health

At startup the lifespan first checks that `STORAGE_LOCAL_DIR` and `CHROMA_PATH` are writable (the app refuses to start otherwise), then connects Mongo (`maxPoolSize` 10, `serverSelectionTimeoutMS` 5000, `socketTimeoutMS` 20000), ensures the indexes, opens the vector store, and, when `SEED_ON_STARTUP` is set, runs the self-healing seed (a failure is logged and the app still starts). `GET /api/health/live` answers without touching a database (the container and ALB check); `GET /api/health` is readiness: a Mongo ping and the vector store, each under about 2 s, plus the seed result, answering 503 when any fails. Both live under `/api` (the SPA catch-all serves everything else). uvicorn runs with `--proxy-headers`, `FORWARDED_ALLOW_IPS`, `--timeout-keep-alive 130`, and `--timeout-graceful-shutdown 25`.

### Image card (Phase 1b — proves the design system)
- Same (hybrid) retrieval. Card copy streams as **natural text** into a lightweight **React** preview for the live "typing" effect; the final **structured fields** (`eyebrow/headline/body/cta/hashtag`) come from a **structured-output** call (JSON matching a strict schema, DECISIONS #40; cleaner than parsing `<<markers>>` mid-stream). The terminal `meta` carries `suggested_keywords` + retrieval data.
- **Image selection is a parallel step** (does not block copy): client feeds Claude's `suggested_keywords` to the Unsplash proxy, user picks one (or uploads). Mandatory attribution is attached.
- Each archetype (`cards/PhotoLed|Statement|Quote`) is authored in **Satori's flexbox/CSS subset** with **workspace fonts/colors only** (brand fonts loaded as font **buffers**). The *same* Satori definition produces both the locked final preview and the export: `useCardExport` runs Satori → SVG → `@resvg/resvg-wasm` → exact **1080×1350 PNG**, attribution baked in. **Preview == export by construction.** (The streaming "typing" preview can be a plain React card; the final/exported card is Satori.)

---

## 6. API surface

All under `/api`. JWT bearer (EMS `HTTPBearer`). Workspace-scoped routes go through `get_workspace_or_404`, which also enforces `owner_id == current_user`.

Workspace-scoped paths below are shortened to `…` for `/workspaces/{id}`.

| Group | Endpoints |
|---|---|
| auth | `POST /auth/login` (development only; 404 in production; refuses the demo user) · `POST /auth/demo-login` (Turnstile-checked visitor start) · `GET /auth/me` |
| status | `GET /status` (no auth; live-AI availability, Turnstile site key, password sign-in open) |
| examples | `GET /examples` (no auth; the demo brand and the four read-only examples) · `GET /examples/{id}/download/{fmt}` |
| workspaces | `GET/POST /workspaces` · `GET/PATCH/DELETE /workspaces/{id}` · logo `POST/DELETE …/logo` · `POST …/brand/extract` · exemplars `POST …/exemplars` `DELETE …/exemplars/{eid}` · brand-images `POST …/brand-images` `PATCH/DELETE …/brand-images/{iid}` · fonts `POST …/fonts` `DELETE …/fonts/{fid}` `GET …/fonts/file/{fid}/{name}` · card-presets `POST …/card-presets` `DELETE …/card-presets/{pid}` |
| assets | `POST …/assets` (202 + BackgroundTask) · `GET …/assets` · `POST …/assets/{aid}/reingest` · `GET/DELETE …/assets/{aid}` |
| templates | `POST …/templates` (upload) · `GET …/templates` · `DELETE …/templates/{tid}` · `POST …/templates/{tid}/ai-fill` · `POST …/templates/{tid}/fill-from-document` · `POST …/templates/{tid}/render` |
| generate (SSE) | `POST …/generate/text` · `POST …/generate/card` · `POST …/generate/post` · `POST …/generate/document` |
| generations | `GET …/generations?type=` · `GET …/generations/count` · `GET/PATCH/DELETE …/generations/{gid}` · `GET …/generations/{gid}/download/{fmt}` |
| images | `GET /images/unsplash/search?q=&page=` · `POST /images/unsplash/track` · `POST …/images/upload` · `GET …/images/file/{iid}/{name}` |
| health | `GET /health/live` → `{status}` (liveness, no database) · `GET /health` → `{status, mongo, vector_store, seed}` (readiness, 503 when not ready) |

List endpoints page with `?limit=&offset=` and return `{items, next_offset}` (generations default to 24, assets to 30, max 100); `GET …/generations?type=` takes `all|text|card|document|post_pack`. The interactive API docs (`/docs`, `/redoc`, `/openapi.json`) are off in production.

Generations are **persisted server-side at stream end**; `PATCH` is for the Phase 1.5 inline edits (copy, layout, per-card accent). Document renders are served from the `download` route, not re-generated.

### Security and limits

- **Rate limits** (slowapi, per IP, in-memory and per instance): `RATE_LIMIT_AUTH` 10/minute on sign-in,
  `RATE_LIMIT_GENERATE` 30/minute on AI routes. With exactly one task in production (DECISIONS #46), the in-memory limits see all traffic.
- **AI spend:** every paid call is reserved in the dollar ledger first (section 5a); over the budget a visitor
  gets a friendly 429 or 503 that points at the examples. Demo starts are limited per IP
  (`DEMO_STARTS_PER_HOUR`, `DEMO_STARTS_PER_DAY`) and checked by Turnstile; Unsplash search is limited to
  `RATE_LIMIT_UNSPLASH` per IP.
- **Demo protection:** `require_not_demo` blocks every workspace, brand, logo, font, preset, template, asset,
  and image-upload change for the demo user; generation is still allowed, and a visitor can delete their own
  generations (never an example).
- **Security headers:** a CSP (`CSP_MODE` = `enforce` by default, or `report-only` / `off`; DECISIONS #36) on
  every response, plus HSTS in production.
- **Secrets:** API keys, the JWT secret, and the Mongo URL are `SecretStr`, so they never print in logs or
  tracebacks. In production the server refuses to start with the default JWT secret or one shorter than 32
  characters.
- **Upload caps** live in `app/limits.py`: images 8 MB, assets, templates and source documents 10 MB, fonts
  5 MB; PDFs up to 80 pages; up to 400 chunks per document; zip-bomb guards for .docx/.pptx; and the per-workspace
  caps (5 example cards, 24 brand images, 8 fonts, 8 card presets).

---

## 7. Risks / gotchas

1. **Card must not inherit app fonts.** The card uses only `brand_profile.fonts`; render it in a container that explicitly sets `font-family` and never inherits the global Plus Jakarta Sans / DM Mono. Add a Vitest assertion on computed font-family. (Top forbidden anti-pattern, DESIGN §7.)
2. **Card export fidelity (Satori).** Satori supports a *subset* of CSS (flexbox + common text/border/background props) — author the 3 archetypes within it from day one. Load each workspace brand font as a font **buffer** and pass it to Satori: curated fonts come as fontsource TTFs from jsDelivr (`styles/brandFonts.ts`), uploaded `.ttf` fonts come from the API, and a bundled Lora is the fallback (DECISIONS #34). Using one Satori definition for both preview and export guarantees parity; the Unsplash image is embedded by URL/data — confirm CORS allows it. There is no server-side screenshot fallback, so every layout must stay within what Satori supports.
3. **SSE buffering.** Reuse EMS frame shape exactly. Client uses fetch + `ReadableStream` (needs POST body + JWT header — `EventSource` can't do either). Set `X-Accel-Buffering: no` for `text/event-stream` behind Vite proxy / ALB / CloudFront. Always emit a terminal frame in `finally` so the client unsticks on error.
4. **Unsplash attribution is mandatory.** Required field on `image.source == "unsplash"`, rendered on the card DOM **and** in the picker (never a tooltip). Fire Unsplash's download-tracking endpoint on selection (license requirement) in `unsplash_service`.
5. **Demo corpus quality = the demo.** A thin corpus produces generic output and makes RAG look pointless. The rich Verdure corpus (see [demo-corpus/](./demo-corpus/)) is a real Phase 1a deliverable.
6. **Embedding dim 1536.** Pin `embedding_dim` in config and at collection creation in both stores. Store `embedding_model` + `embedding_dim` on the workspace so a model change forces a re-ingest rather than mixing dims (which silently corrupts similarity).
7. **Workspace isolation enforced server-side.** Every query passes `workspace_id`; each workspace has its own Chroma collection, so the collection name is the tenant boundary. Never query across collections, and keep a cross-leak pytest (`test_query_is_workspace_scoped`).
8. **Card structured output.** Get the final card fields via **structured output** (`output_config.format` with a strict schema; a forced `tool_choice` is rejected by Claude Sonnet 5.5, DECISIONS #40), not by parsing streamed JSON/markers mid-flight. Stream natural text for the live typing effect; read fields + `suggested_keywords` from the completed response.
9. **Untrusted ingested content.** Treat uploaded brand docs as untrusted: delimit retrieved chunks in the prompt as data-not-instructions (see §5), and cap PDF **size / page-count / parse-time** to avoid a malicious-file DoS.
10. **Empty / thin corpus.** A workspace with no ready chunks must degrade gracefully — block generation with a clear "ingest assets first" state rather than calling Claude with no brand context.
11. **Demo seed protection.** In `is_demo` context, block every change to the seeded workspace (workspace, brand, logo, fonts, presets, templates, assets, image uploads; see Security and limits) so visitors can't break the seeded Verdure corpus. The UI disables those controls and shows a demo notice; the server enforces it with `require_not_demo`.
