# AWS Infrastructure & AI Deployment Plan
## James Littlefield — Portfolio Projects

> **This is the canonical infrastructure doc** for all portfolio AI projects, and the source the project-level [`DECISIONS.md`](./DECISIONS.md) defers to on hosting, vector store, and databases. Note: **Brand Content Studio is being built local-first** — Chroma + Docker MongoDB + local filesystem storage, no AWS required — and only deploys into the shared platform below at the deployment phase (Phase 3). See [`PLAN.md`](./PLAN.md).

---

## Current Project Inventory

| Project | Stack | AI Pattern | Status |
|---|---|---|---|
| Portfolio site | Vue 3, Docker | None | Live — jameslittlefield.net |
| Barcode Generator | Vue 2, Node/Express, MongoDB, Docker | None | Live — barcode.jameslittlefield.net |
| Employee Management System | Vue 3, FastAPI, MongoDB, Docker | Tool Use / Function Calling | Live — employees.jameslittlefield.net · AI to be added |
| Smart Resume Builder | React, Django, PostgreSQL, Docker | Prompt → Response | Built · not yet deployed |
| Brand Content Studio | React, FastAPI, MongoDB, Qdrant, Docker | RAG | Design complete · not yet built |

---

## Architecture Philosophy

One shared AWS platform, many projects. Rather than isolated infrastructure per project, all projects share a common ECS cluster, database instances, and secrets setup. Each project deploys as its own ECS service with its own S3 bucket and CloudFront distribution.

This means:
- One ECS Fargate cluster hosts all backend services
- One MongoDB instance shared across all MongoDB projects (one database per project)
- One Qdrant instance shared across all RAG projects (one collection per project)
- One PostgreSQL instance for Smart Resume Builder (and future projects if applicable)
- Per-project S3 buckets and CloudFront distributions
- One Secrets Manager setup, namespaced per project

---

## Shared Infrastructure Layer

### Container Platform
- **AWS ECS Fargate** — shared cluster, all backends run here as separate services
- Each project is its own ECS service with its own task definition and Docker image
- All projects already use Docker — ECS is the natural deployment target

### Databases

**MongoDB (shared instance)**
Projects using it: Barcode Generator, Employee Management System, Brand Content Studio
- One MongoDB container on ECS or EC2 t3.small
- One database per project: `barcode`, `ems`, `brand_content`
- Note: Confirm whether current MongoDB instances are truly self-hosted or on Atlas free tier — consolidate to one instance before deploying new projects

**PostgreSQL (shared instance)**
Projects using it: Smart Resume Builder
- One PostgreSQL container on ECS or RDS t3.micro
- One database per project: `resume_builder`
- Future: any new project that fits a relational data model can use this instance
- Future: pgvector extension available if a future RAG project pairs naturally with PostgreSQL data (eliminates need for separate vector DB)

**Qdrant (shared instance — all RAG projects)**
Projects using it: Brand Content Studio + all future RAG projects
- One Qdrant container on ECS (t3.small is sufficient for portfolio scale)
- One collection per project: `brand-content-studio`, and future RAG project collections
- Cost: ~$15-20/month shared across all RAG projects regardless of count
- Why not Pinecone: Pinecone free tier is one index total, and paid plans are $70/month per index. At 3-5 RAG projects that becomes $210-350/month. Qdrant self-hosted eliminates this cost entirely.
- Development: use Chroma locally (runs in memory, zero setup) and deploy with Qdrant

### Secrets
- **AWS Secrets Manager** — one setup, namespaced per project
- Format: `{project-name}/{secret-name}` e.g. `brand-content-studio/anthropic-api-key`
- All Docker containers receive secrets as environment variables at runtime

### CDN & Static Hosting
- **S3 + CloudFront** — per-project bucket and distribution
- All frontend builds deploy here
- Same pattern already in use across existing projects

---

## Per-Project Deployment Configuration

### Portfolio Site (jameslittlefield.net)
```
Frontend:  S3 + CloudFront
Backend:   None
Database:  None
Tags:      project: portfolio | env: production
```

### Barcode Generator (barcode.jameslittlefield.net)
```
Frontend:  S3 + CloudFront
Backend:   Node/Express on ECS Fargate (shared cluster)
Database:  Shared MongoDB instance — database: barcode
Tags:      project: barcode-generator | env: production
```

### Employee Management System (employees.jameslittlefield.net)
```
Frontend:  S3 + CloudFront
Backend:   FastAPI on ECS Fargate (shared cluster)
Database:  Shared MongoDB instance — database: ems
AI:        Claude API (Tool Use) — key in Secrets Manager
Tags:      project: ems | env: production
```

### Smart Resume Builder (not yet deployed)
```
Frontend:  S3 + CloudFront
Backend:   Django on ECS Fargate (shared cluster)
Database:  Shared PostgreSQL instance — database: resume_builder
AI:        Claude API (Prompt → Response) — key in Secrets Manager
Tags:      project: smart-resume-builder | env: production
```

### Brand Content Studio (not yet built)
```
Frontend:  S3 + CloudFront
Backend:   FastAPI on ECS Fargate (shared cluster)
Database:  Shared MongoDB instance — database: brand_content
Vector DB: Shared Qdrant — collection: brand-content-studio
File:      S3 bucket (brand assets + uploaded images)
AI:        Claude API (RAG generation) + OpenAI text-embedding-3-small
Secrets:   brand-content-studio/anthropic-api-key
           brand-content-studio/openai-api-key
           brand-content-studio/unsplash-access-key
Tags:      project: brand-content-studio | env: production
```

> **Local development** (the current phase): Chroma (vector store) + Docker MongoDB + local filesystem storage, all via `docker-compose`. The vector store and file storage sit behind swappable interfaces, so moving to the shared Qdrant + S3 above is a config flip (`vector_store_backend=qdrant`, `storage_backend=s3`). No AWS resources are provisioned until the deployment phase.

---

## AI Integration by Project

### Prompt → Response (Smart Resume Builder)
- Simplest pattern — text in, text out
- FastAPI or Django endpoint calls Claude API with constructed prompt
- Stream response back to frontend via Server-Sent Events
- No vector database needed
- No embedding model needed

### Tool Use / Function Calling (EMS AI Chatbot)
- AI decides which data to fetch based on user's natural language query
- Define tool schemas wrapping existing MongoDB queries
- Claude calls tools, receives results, reasons over them, responds
- FastAPI handles the tool execution loop
- No vector database needed
- No embedding model needed

### RAG (Brand Content Studio + future RAG projects)
- Two-phase: ingestion (one time) and generation (every query)
- Ingestion: chunk documents (standalone `langchain-text-splitters`) → OpenAI embeddings → vector store (Chroma dev / Qdrant prod)
- Generation: embed query → Qdrant similarity search → retrieved chunks + prompt → Claude
- Shared Qdrant instance — one collection per project
- OpenAI text-embedding-3-small for embeddings (Anthropic does not offer embedding models)
- Hand-rolled orchestration — OpenAI/Anthropic SDKs + the vector-store client directly; only the standalone `langchain-text-splitters` (full LangChain deliberately avoided; see `docs/DECISIONS.md`)

---

## Deployment Sequencing

### Phase 1 — Deploy Smart Resume Builder (next)
Deploy standalone. Do not wait to build shared infrastructure first.
- Set up ECS Fargate service for Django backend
- Set up PostgreSQL on ECS or RDS
- Deploy frontend to S3 + CloudFront
- Add API keys to Secrets Manager with `smart-resume-builder/*` namespace
- Tag everything: `project: smart-resume-builder`

### Phase 2 — Add AI to EMS (after Smart Resume Builder deployed)
Extend existing deployed project.
- Add Claude API key to Secrets Manager: `ems/anthropic-api-key`
- Add tool use endpoints to existing FastAPI backend
- Redeploy ECS service
- No new infrastructure needed

### Phase 3 — Build shared platform + deploy Brand Content Studio
This is the moment to build the shared platform properly.
- Spin up shared ECS cluster
- Migrate Barcode Generator and EMS backends into shared cluster
- Spin up shared Qdrant ECS task
- Consolidate MongoDB instances (Barcode + EMS + Brand Content) into one
- Deploy Brand Content Studio as a new ECS service
- Set up CDK or Terraform to define all infrastructure as code going forward

### Phase 4 — All future projects
Adding a new project is adding a new ECS service and connecting to shared databases. Marginal infrastructure cost is near zero.

---

## Infrastructure as Code

Once Phase 3 is reached, define all infrastructure in AWS CDK (TypeScript).

Why CDK over Terraform:
- TypeScript — same language you already use on the frontend
- AWS-native — better integration with ECS, Secrets Manager, CloudFront
- Easier to share constructs across projects

Recommended structure:
```
/infrastructure
  lib/
    shared-stack.ts          — ECS cluster, MongoDB, Qdrant, Secrets Manager, VPC
    portfolio-stack.ts        — Portfolio site S3 + CloudFront
    barcode-stack.ts          — Barcode Generator service
    ems-stack.ts              — EMS service
    resume-builder-stack.ts   — Smart Resume Builder service
    brand-content-stack.ts    — Brand Content Studio service
  bin/
    app.ts                    — entry point
```

---

## AWS Tagging Convention

Apply to every resource without exception. Enables per-project cost tracking in AWS Cost Explorer.

| Tag key | Example values |
|---|---|
| `project` | `portfolio`, `barcode-generator`, `ems`, `smart-resume-builder`, `brand-content-studio` |
| `env` | `production`, `staging`, `development` |

---

## Total Estimated Monthly Cost (all projects running)

| Resource | Cost |
|---|---|
| ECS Fargate (shared cluster, all services) | ~$15-30/month |
| Qdrant ECS task (shared, all RAG projects) | ~$15-20/month |
| MongoDB instance (shared, all projects) | ~$10-15/month |
| PostgreSQL instance (shared) | ~$10-15/month |
| S3 + CloudFront (all projects combined) | ~$2-5/month |
| Secrets Manager | ~$1-2/month |
| Claude API (all projects) | ~$15-30/month |
| OpenAI Embeddings (RAG projects) | ~$2-5/month |
| **Total** | **~$70-120/month for everything** |

This covers 5 live projects with AI features across all three AI integration tiers.

---

## Key Decisions & Rationale

**ECS Fargate over Lambda for backends**
All existing projects use Docker. Lambda via Mangum works but cold starts affect streaming responses. ECS is the more natural fit for containerized backends and handles streaming cleanly.

**Qdrant over Pinecone for RAG**
Pinecone free tier = one index total. At 3-5 RAG projects on paid plans = $210-350/month. One shared Qdrant ECS task costs $15-20/month regardless of how many RAG projects use it.

**Chroma for local RAG development**
Runs in memory, zero configuration. Use Chroma locally and Qdrant in production for all RAG projects.

**pgvector as future option**
If a future project pairs naturally with PostgreSQL, pgvector eliminates the need for a separate vector database entirely. Already available on the shared PostgreSQL instance.

**Shared MongoDB over Atlas free tier**
Atlas free tier is limited and the self-hosted approach already in use across existing projects gives full control. One shared instance is cheaper and simpler than multiple Atlas free tier clusters.

**FastAPI as the standard AI backend**
All new AI projects use FastAPI. It handles async and streaming responses better than Django. Smart Resume Builder uses Django since it's already built — leave it. All future projects use FastAPI.
