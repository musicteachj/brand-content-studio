# Brand Content Studio

A **RAG-powered** brand content studio. It ingests a brand's own material (voice and tone guides, past
LinkedIn posts, content pillars, personas, competitor notes), embeds and indexes it per workspace, and then
**retrieves the relevant brand context at generation time**, so Claude writes content that sounds like the
brand instead of like a generic model.

From one brief it produces:

- **LinkedIn posts:** a ready-to-paste caption plus a matching designed card.
- **Text posts** in a chosen tone and length.
- **Image cards:** 1080 × 1350 PNGs in three layouts (photo-led, statement, quote), in the brand's colors and
  fonts, with Unsplash or your own photos.
- **Documents:** a branded one-pager (.docx and PDF) or a short slide deck (.pptx).
- **Filled templates:** upload your own branded .docx or .pptx with `{{placeholders}}` and fill it by hand, from
  a brief, or from another document.

Retrieval is the differentiator: generic generation is prompt → response, while on-brand generation needs the
brand corpus pulled in at query time. Every generation shows exactly which brand chunks it used.

> **Status:** all six build phases (text posts through robustness and limits) are merged into `dev`, the
> integration branch, along with a security audit and an October QA pass, and the demo-readiness work (private
> visitor sessions, an AI spend ledger, a self-healing seed, health checks, and a production-style compose file)
> is built. `main` still holds the Phase 0 scaffold; the first release and the AWS deployment are still to come
> (see [`docs/DEPLOY.md`](./docs/DEPLOY.md)). See [`CHANGELOG.md`](./CHANGELOG.md) and
> [`docs/PLAN.md`](./docs/PLAN.md).

## Screenshots

| | |
|---|---|
| ![LinkedIn post: caption and matching card](./docs/screenshots/linkedin-post.jpg) | ![Retrieved context: the brand chunks behind a text post](./docs/screenshots/retrieved-context.jpg) |
| **LinkedIn post:** caption plus a matching card from one brief | **Retrieved context:** the brand chunks behind each generation, with scores |
| ![Image card with the Customize panel](./docs/screenshots/image-card.jpg) | ![Branded one-pager document](./docs/screenshots/document.jpg) |
| **Image card:** brand layouts, then customize, edit text, and export | **Document:** a branded one-pager, downloadable as .docx and PDF |
| ![Content History in dark mode](./docs/screenshots/history-dark.jpg) | ![Brand identity settings](./docs/screenshots/brand-identity.jpg) |
| **History** (dark mode): every generation, re-downloadable | **Brand identity:** palette, fonts, voice, and logo |

Screenshots use the "Verdure Materials" demo brand and a made-up user.

## Features

- **Generate** in four modes (LinkedIn post, text post, image card, document). Output streams in live over SSE,
  and a **Retrieved context** panel lists the brand chunks used.
- **Card customization** without another model call: swap the layout, change the accent color, edit the text on
  the card, change the picture, or apply a saved card preset.
- **Image picker:** Unsplash search (with the required attribution), the workspace's brand image library, or
  your own upload.
- **History** of every generation, filterable by type, with re-download and a "Customize" path back into
  Generate.
- **Asset Manager:** upload PDF, Markdown, or text files by kind (voice, past posts, pillars, personas,
  competitors, other) and watch each one ingest.
- **Templates:** bring your own branded .docx or .pptx and fill its placeholders by hand, with "Draft with AI",
  or from an uploaded document. The output keeps the template's own styling.
- **Brand setup in Settings:** palette, fonts (curated list or your own .ttf uploads), voice summary, logo,
  "Learn from an image" (Claude proposes a palette, fonts, and voice from an uploaded logo or guideline page),
  example cards that steer the copy style, brand images, and card presets.
- **Workspaces:** one per brand, with a switcher in the top bar.
- **Light and dark themes**, plus an optional tint that dresses the app in the active brand's color.
- **The demo:** one click on "Try it live" (after a Cloudflare Turnstile check) starts a private visitor session
  in the seeded Verdure workspace. It lasts 24 hours, each visitor sees only their own History plus four
  read-only ready-made examples (open to everyone at `/examples`, no live AI needed), and live generation is
  paced by an AI dollar budget, so when it is used up the studio points at the examples instead.
- Desktop-first: the minimum supported width is 1024 px; below that the sidebar collapses to icons.

## Stack

- **Frontend:** React 19 + Vite 8 + TypeScript, Tailwind CSS 4 + shadcn/ui (Radix), Zustand, TanStack Query,
  react-hook-form + zod, lucide-react. Cards are rendered in the browser with Satori and resvg-wasm.
- **Backend:** Python 3.12, FastAPI + Motor (async MongoDB) + Pydantic v2, slowapi rate limiting.
- **AI:** Claude `claude-sonnet-5-5` (`AsyncAnthropic`, streamed over SSE) for generation, brand extraction from
  images, and template drafting; OpenAI `text-embedding-3-small` for embeddings.
- **RAG:** hand-rolled ingestion (standalone `langchain-text-splitters` for chunking, no full framework) and a
  vector store behind a swappable interface: **Chroma**, running in-process on local disk (no Chroma server).
- **Documents:** python-docx, python-pptx, and reportlab; docxtpl for template filling.
- **Images:** Unsplash API (server-proxied, mandatory attribution) plus uploads.
- **Auth:** JWT (PyJWT). Visitors start a 24-hour demo session behind a Turnstile bot check; password sign-in
  exists for development only (`/api/auth/login` is a 404 in production). There is no public sign-up.

Local development is fully decoupled from the cloud; the AWS deployment is still to come. See
[`docs/DECISIONS.md`](./docs/DECISIONS.md).

## Monorepo layout

```
client/      React + Vite SPA
server/      FastAPI + RAG pipeline (app/rag, app/services, app/routes, app/prompts) and the demo seed (seed/)
docs/        Planning and reference docs, the demo corpus, design system, mocks, and screenshots
Dockerfile   Production image: builds the client and serves it from the API on port 8000
```

## Local development

**Prerequisites:** Node 24 (see `.nvmrc`), Python 3.12, and Docker.

```bash
# 1. Database: MongoDB on 127.0.0.1:27017 (the only thing docker compose runs;
#    Chroma runs inside the API server, in `server/chroma/`)
docker compose up -d

# 2. Server: virtual environment, dependencies, and settings
cd server
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt   # includes requirements.txt
cp .env.example .env                            # then fill in the keys (see below)
cd ..

# 3. Client and root tooling (two separate installs)
npm install
(cd client && npm install)

# 4. Run the client (http://localhost:5173) and the API (http://localhost:8000)
npm run dev
```

Open http://localhost:5173 and choose **Try it live**. The API seeds itself at startup
(`SEED_ON_STARTUP=true` in `.env.example`): it builds the demo user, the Verdure Materials workspace with its
corpus, and the four ready-made examples on a fresh database, repairs anything missing on later starts, and
makes no paid call (the vectors and examples come from checked-in fixtures). `npm run seed` does the same on
demand; stop the API first, because only one process may open the Chroma directory. In development a blank
Turnstile key pair means Cloudflare's always-pass test keys, answered locally. The API's interactive docs are
at http://localhost:8000/docs in development.

**Settings in `server/.env`** (every key is listed in `server/.env.example`):

| Key | Default | Needed for |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | All generation, brand extraction, and template drafting |
| `OPENAI_API_KEY` | none | Embeddings: ingesting assets and retrieval at generation time (the seed needs none) |
| `UNSPLASH_ACCESS_KEY` | none | Optional. Without it, image search shows an error; uploads still work |
| `JWT_SECRET_KEY` | a placeholder | Token signing. In production it must be at least 32 characters and not the default |
| `AI_MODEL` | `claude-sonnet-5-5` | Optional. Requests are shaped for Sonnet 5.5 (DECISIONS #40), so if an older `.env` still sets `claude-sonnet-4-6`, update the line or remove it |
| `AI_EFFORT` | `low` | Optional. How much the model thinks before writing: `low`, `medium`, or `high` |
| `AI_MONTHLY_BUDGET_USD` | `10` | The month's AI spend cap in dollars; `0` turns live AI off (every AI action gets the free-path message) |
| `AI_PACING_MULTIPLIER` | `3` | A day may spend up to this many times an even share of what is left this month |
| `AI_DAILY_FLOOR_USD` | `0.50` | The least a day may spend, so late in the month the demo still works |
| `AI_VISITOR_BUDGET_USD` | `0.15` | Per visitor session: a call is admitted while the visitor's spend so far is below this (one call may go over) |
| `DEMO_STARTS_PER_HOUR` | `15` | Demo starts per IP per hour |
| `DEMO_STARTS_PER_DAY` | `50` | Demo starts per IP per day |
| `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` | blank | The bot check on each demo start. Blank in development means Cloudflare's test keys; production requires real keys |
| `APP_ORIGIN` | `http://localhost:5173` | Where visitors reach the app; Turnstile tokens must be issued for this host. Production requires https |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Proxies whose `X-Forwarded-For` is trusted (IPs or CIDRs). In production, the load balancer's VPC CIDR; never `*` or a `/0` network |
| `SEED_ON_STARTUP` | `true` in `.env.example`, off if unset | Check and repair the demo seed when the API starts |
| `CHROMA_PATH` | `./chroma` | The Chroma data directory; one process per directory |
| `DATABASE_NAME` | `folio` | The MongoDB database (an older `.env` keeps its own value) |
| `MONGO_MAX_POOL_SIZE` | `10` | The Mongo connection pool (server selection times out at 5 s, sockets at 20 s) |

Keep `VECTOR_STORE_BACKEND=chroma` and `STORAGE_BACKEND=local`; the S3 option isn't implemented yet.

**Your own account:** there's no sign-up screen. The demo user can generate but can't change the workspace or
brand, so to try uploads and the brand editor, add a user directly in MongoDB (see the seed script for the user
shape). Password sign-in (`POST /api/auth/login`) is for those accounts in development only; the demo user can't
use it.

## Quality checks

From the repo root:

```bash
npm run lint        # eslint + ruff
npm run typecheck   # tsc + mypy
npm test            # vitest + pytest (integration tests run when Mongo is up; the vector store is faked)
npm run build       # client production build
npm run ci          # all of the above
```

`cd client && npm run format` checks formatting with Prettier. CI (`.github/workflows/ci.yml`) also builds and
boots the Docker image and runs dependency audits.

## Production image

`docker build .` produces one image that serves the built client and the API on port 8000 (non-root, uid 10001,
with a health check on `/api/health/live`). It needs an external MongoDB and persistent volumes at `/app/storage`
and `/app/chroma` (Chroma runs inside the container, so run exactly one copy), plus production settings. To run
it locally the way production does (read-only root filesystem, no capabilities, live AI off):

```bash
export JWT_SECRET_KEY=$(openssl rand -hex 32)
docker compose -f docker-compose.prod.yml up -d --build   # http://localhost:8000
```

[`docs/DEPLOY.md`](./docs/DEPLOY.md) has the ECS settings, the seed report, restore notes, and the go-live
checklist. Rate limiting is in-memory and per instance.

## Documentation

| Doc | What it covers |
|---|---|
| [`docs/PLAN.md`](./docs/PLAN.md) | **Start here:** phased build roadmap with acceptance criteria |
| [`CHANGELOG.md`](./CHANGELOG.md) | What's shipped, by phase |
| [`docs/WORKFLOW.md`](./docs/WORKFLOW.md) | How we build: vertical slices, front/back ordering, branching, commits |
| [`docs/DECISIONS.md`](./docs/DECISIONS.md) | Single source of truth for architecture decisions |
| [`docs/DEPLOY.md`](./docs/DEPLOY.md) | The production image, local production run, ECS settings, and go-live checklist |
| [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) | Stack, repo structure, RAG pipeline, API surface, security, gotchas |
| [`docs/DATA_MODEL.md`](./docs/DATA_MODEL.md) | MongoDB collections and the vector-store schema |
| [`docs/DESIGN.md`](./docs/DESIGN.md) | "Folio" design system (tokens, type, components) |
| [`docs/demo-corpus/`](./docs/demo-corpus/) | The "Verdure Materials" demo brand corpus |
| [`docs/mocks/`](./docs/mocks/) | The original June 2026 Folio design mocks (reference only; the app has moved on) |
| [`docs/screenshots/`](./docs/screenshots/) | Current screenshots used in this README |
| [`docs/AUDIT-2026-07.md`](./docs/AUDIT-2026-07.md), [`docs/QA-2026-10.md`](./docs/QA-2026-10.md) | The July security audit and the October QA pass |
| [`docs/brand_content_studio_spec.md`](./docs/brand_content_studio_spec.md) | Original product spec (recalibrated) |
| [`docs/aws_infrastructure_plan.md`](./docs/aws_infrastructure_plan.md) | Shared AWS platform for all portfolio AI projects |

## License

TBD.
