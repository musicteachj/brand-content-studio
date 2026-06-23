# Brand Content Studio

A **RAG-powered** brand content studio. It ingests a brand's assets — voice/tone guides, past LinkedIn posts, content pillars, personas, competitor notes — embeds and indexes them per workspace, then **retrieves the semantically relevant brand context at generation time** so Claude produces on-brand LinkedIn **text posts** and **designed image cards** (1080×1350 PNG, ready to publish).

Retrieval is the differentiator: generic generation is prompt→response; on-brand generation needs the brand corpus pulled in at query time.

> **Status:** Phase 0 (scaffold, `v0.0.0`) complete — see [`CHANGELOG.md`](./CHANGELOG.md). Roadmap in [`docs/PLAN.md`](./docs/PLAN.md).

## Portfolio context

The 3rd of three AI portfolio projects, each demonstrating a different AI pattern:

| Project | AI pattern |
|---|---|
| Smart Resume Builder | Prompt → Response |
| Employee Management System (AI chatbot) | Tool Use / Function Calling |
| **Brand Content Studio** | **RAG (Retrieval Augmented Generation)** |

## Stack

- **Frontend:** React + Vite + TypeScript, Tailwind + shadcn/ui, Zustand, react-query, react-hook-form + zod, lucide-react
- **Backend:** FastAPI + Motor (async MongoDB) + Pydantic v2
- **AI:** Claude `claude-sonnet-4-6` (`AsyncAnthropic`, streamed over SSE) for generation; OpenAI `text-embedding-3-small` for embeddings
- **RAG:** hand-rolled ingestion (standalone `langchain-text-splitters` for chunking, no full framework); vector store behind a swappable interface — **Chroma** (local dev) / **Qdrant** (production)
- **Images:** Unsplash API (server-proxied, mandatory attribution) + user upload
- **Auth:** JWT (python-jose) with a seeded demo user + "Explore as demo" bypass

Local dev is fully decoupled from the cloud; AWS deployment is deferred. See [`docs/DECISIONS.md`](./docs/DECISIONS.md).

## Monorepo layout

```
client/      React + Vite SPA
server/      FastAPI + RAG pipeline (app/rag, app/services, app/routes, app/prompts)
docs/        Planning & reference docs, demo corpus, and design mocks (docs/mocks/)
```

## Documentation

| Doc | What it covers |
|---|---|
| [`docs/PLAN.md`](./docs/PLAN.md) | **Start here** — phased build roadmap with acceptance criteria |
| [`CHANGELOG.md`](./CHANGELOG.md) | What's shipped, by phase |
| [`docs/WORKFLOW.md`](./docs/WORKFLOW.md) | How we build — vertical slices, front/back ordering, branching, commits |
| [`docs/DECISIONS.md`](./docs/DECISIONS.md) | Single source of truth for architecture decisions |
| [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) | Stack, repo structure, RAG pipeline, API surface, gotchas |
| [`docs/DATA_MODEL.md`](./docs/DATA_MODEL.md) | MongoDB collections + vector-store schema |
| [`docs/demo-corpus/`](./docs/demo-corpus/) | The "Verdure Materials" demo brand corpus |
| [`docs/DESIGN.md`](./docs/DESIGN.md) | "Folio" design system (tokens, type, components) |
| [`docs/mocks/`](./docs/mocks/) | Folio HTML design mocks (reference only) |
| [`docs/brand_content_studio_spec.md`](./docs/brand_content_studio_spec.md) | Original product spec (recalibrated) |
| [`docs/aws_infrastructure_plan.md`](./docs/aws_infrastructure_plan.md) | Shared AWS platform for all portfolio AI projects |

## Local development

> Quickstart to be filled in once Phase 0 scaffolding lands. Planned shape:

```bash
docker-compose up -d      # mongo:7 + chromadb/chroma
npm install               # root, runs client + server via concurrently
python -m seed.seed_demo  # seed demo user + Verdure workspace + corpus
npm run dev               # client + FastAPI server
```

## License

TBD.
