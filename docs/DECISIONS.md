# Decisions — Single Source of Truth

> This file is the **canonical record** of the architectural decisions for Brand Content Studio.
> When any other document (including `brand_content_studio_spec.md`) disagrees with this file, **this file wins**.
> Related: [PLAN.md](./PLAN.md) · [ARCHITECTURE.md](./ARCHITECTURE.md) · [DATA_MODEL.md](./DATA_MODEL.md) · [DESIGN.md](./DESIGN.md) · [aws_infrastructure_plan.md](./aws_infrastructure_plan.md)

Last recalibrated: 2026-06-22.

---

## Why this file exists

The project accumulated three planning docs written at different times. The original `brand_content_studio_spec.md` predates the reconsidered `aws_infrastructure_plan.md`, so the two contradicted each other on the vector store, backend hosting, and database. This file resolves every conflict once, and the other docs were edited to point here.

The product itself is unchanged: a **RAG**-powered studio that ingests a brand's assets, retrieves the semantically relevant pieces at generation time, and has Claude produce on-brand LinkedIn **text posts** and **designed image cards**. RAG is the differentiator and the whole point of this portfolio piece.

---

## Decisions table

| # | Area | Decision | Supersedes (now stale) | Rationale |
|---|---|---|---|---|
| 1 | Vector store | **Chroma (local dev) / Qdrant (prod)** behind a `VectorStore` protocol; per-workspace isolation | ❌ Pinecone | Pinecone free tier = 1 index; paid = $70/mo per index. Across 3–5 RAG projects that's $210–350/mo. One shared self-hosted Qdrant is ~$15–20/mo total. Chroma needs zero setup locally. |
| 2 | Backend hosting | **ECS Fargate** (shared cluster); deployment **deferred** — build local-first | ❌ FastAPI on Lambda via Mangum | All sibling projects are Docker-based; Lambda cold starts degrade SSE streaming. ECS streams cleanly. |
| 3 | Frontend | React + Vite + TypeScript + Tailwind + shadcn/ui (Radix + CVA) + Zustand + @tanstack/react-query + react-hook-form + zod + lucide-react | — | Mirrors **Smart Resume Builder** so the portfolio shares one React house style. |
| 4 | Backend | FastAPI + Motor (async MongoDB) + Pydantic v2 | — | Mirrors **Employee Management System**; reuse its auth + SSE streaming patterns. |
| 5 | Generation model | Claude `claude-sonnet-4-6` via `AsyncAnthropic`, **streamed over SSE** | — | Reuse EMS `ai_service.py` streaming pattern verbatim. Streaming token-by-token into the card preview is the demo wow-factor. |
| 6 | Embeddings | OpenAI `text-embedding-3-small` (1536-dim) behind an `Embedder` protocol | — | Anthropic offers no embedding model. The protocol keeps the provider swappable in one file. |
| 7 | App database | **MongoDB** — Docker local for dev, shared self-hosted Mongo in prod | ❌ MongoDB Atlas free tier | Self-hosted shared instance (one DB per project) is cheaper and gives full control; matches sibling projects. |
| 8 | RAG orchestration | **Hand-rolled** pipeline (OpenAI + Anthropic SDKs + the vector-store client directly); only the standalone `langchain-text-splitters` for `RecursiveCharacterTextSplitter`; pdfplumber (pypdf fallback) for PDFs | ❌ full LangChain framework | The pipeline is 4 ops (split→embed→upsert→query); both sibling projects call the SDKs directly, so hand-rolling is lighter, more transparent, and house-consistent. |
| 9 | Auth | python-jose JWT + a **seeded demo user** + an **"Explore as demo" bypass** button; no public signup | ❌ "simple hardcoded auth" | Reuses EMS JWT pattern for portfolio polish while staying minimal (no signup flow). |
| 10 | Demo brand | **Verdure Materials** (eco/materials; forest green `#1C3A2E`, cream `#F4F1E9`, serif type) | ❌ "SDS" | All approved mocks + `DESIGN.md` are built around Verdure. "SDS" is removed everywhere. |
| 11 | Card export | **1080 × 1350** (4:5 portrait) PNG via **Satori** (HTML/JSX→SVG) + **`@resvg/resvg-wasm`** (SVG→PNG), client-side, free, no infra; Playwright server-screenshot as fallback | ❌ 1200×1200; ❌ html2canvas | Satori is deterministic and high-fidelity (powers Vercel OG images); one Satori definition drives both the final preview and the export, so preview == export. html2canvas mis-renders the centerpiece. |
| 12 | Images | Unsplash API (server-proxied) + user upload; **mandatory attribution** rendered automatically | — | Unsplash license requires visible credit. Adobe Firefly's ~$1k/mo minimum rules it out. |
| 13 | File storage | Local filesystem (dev) / S3 (prod) behind a `StorageBackend` protocol | — | Keeps dev zero-dependency; prod swap is config-only. |
| 14 | Build sequence | Phase 0 scaffold → **1a text posts** → **1b image cards** → 1.5 customization → 2 documents → deferred AWS deploy | — | Text posts prove the RAG loop with minimal UI; image cards then prove the design system. |
| 15 | Seed & demo access | Seed the **Verdure** workspace with its corpus **pre-ingested**; "Explore as demo" logs visitors into it with **destructive actions disabled** (`is_demo` guard). No EMS-style demo mode; no public signup. | — | Visitors hit the RAG "wow" instantly with zero setup; the guard protects the seed from being deleted. |
| 16 | Retrieval strategy | **Hybrid**: always inject the brand `voice_summary` + content pillars, then add semantic top-k (k≈6) exemplars | — | Always-needed brand fundamentals shouldn't depend on a similarity hit; naive top-k can miss them. |
| 17 | API cost control | **Hard usage limit set on the Anthropic console** for the project API key (platform-level); in-app per-user caps deferred | — | The console cap bounds spend regardless of demo traffic; SRB-style in-app caps are unnecessary at portfolio scale. |
| 18 | Design approach | Build the frontend UI/UX with the Claude **design skills** (`frontend-design`, `impeccable`, `ui-ux-pro-max`). `DESIGN.md` + the `mocks/` are a **reference / starting point, not a pixel-exact spec** — adopt a better UI/UX option when a skill offers one, and fold the improvement back into `DESIGN.md`. | — | The mocks are AI-generated references; the design skills can produce higher-quality, less-generic UI. Keep Folio's tokens/identity as the baseline and let the system evolve. |

---

## Reconciliations (what changed and where)

- **Pinecone → Qdrant abstraction** — edited in `brand_content_studio_spec.md` (§AI Pattern, §Phase 1, §Tech Stack). `aws_infrastructure_plan.md` already specified Qdrant; no change needed there.
- **Lambda/Mangum → ECS Fargate + local-first** — edited in `brand_content_studio_spec.md` (§Tech Stack, §Build order). Already canonical in `aws_infrastructure_plan.md`.
- **MongoDB Atlas → Docker (dev) / shared self-hosted (prod)** — edited in `brand_content_studio_spec.md` (§Databases).
- **SDS → Verdure Materials** — edited in `brand_content_studio_spec.md` (§What It Is, §Design Identity, §Demo data prep).
- **1200×1200 → 1080×1350** — edited in `brand_content_studio_spec.md` (§LinkedIn Card Design Reference, §Card dimensions).
- **Hardcoded auth → JWT + demo bypass** — edited in `brand_content_studio_spec.md` (§Auth, §Build order).
- **html2canvas → Satori + `@resvg/resvg-wasm`** — card export reconsidered for fidelity and preview==export parity; updated in `ARCHITECTURE.md`, `PLAN.md`, and `brand_content_studio_spec.md` (§Phase 1, §Tech Stack).
- **Full LangChain → hand-rolled pipeline** (standalone `langchain-text-splitters` only) — updated in `ARCHITECTURE.md`, `PLAN.md`, and `brand_content_studio_spec.md` (§Tech Stack).

---

## Deliberately out of scope (for now)

- Public sign-up / multi-user accounts (single owner + demo user only).
- A task queue (Celery/SQS) for ingestion — FastAPI `BackgroundTasks` is sufficient at portfolio scale.
- The AWS shared-platform build (CDK/ECS/Qdrant/Secrets Manager) — documented but **deferred** to the deployment phase per `aws_infrastructure_plan.md` Phase 3.
- Phase 2 document output (`.docx` / `.pptx` / PDF) until Phases 1 and 1.5 ship.

---

## Open questions (revisit before the relevant phase)

- **Card copy streaming** — leaning: stream natural text into a lightweight **React** preview for the live "typing" effect, and obtain the final **structured fields** via an Anthropic **tool-use** call (cleaner than parsing `<<markers>>` mid-stream); render the final/exported card via **Satori**. (Confirm at Phase 1b.)
- **Workspace brand-color UI tint** — the optional `--accent` override (DESIGN §4) needs a trigger: always-on when a workspace is active, or a user toggle. (Decide at Phase 1.5 alongside the accent toggle.)
- **Local image/object storage** — plain local filesystem vs. MinIO (S3-compatible) for dev. Default to filesystem unless S3 parity becomes useful. (Decide at Phase 1a.)
