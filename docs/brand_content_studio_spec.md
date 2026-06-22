# Brand Content Studio — Project Specification

> **Recalibrated 2026-06-22.** This is the original product spec. Where it disagrees with [`DECISIONS.md`](./DECISIONS.md), **DECISIONS.md wins** — it is the single source of truth for architecture choices. The canonical build sequence lives in [`PLAN.md`](./PLAN.md); technical detail in [`ARCHITECTURE.md`](./ARCHITECTURE.md) and [`DATA_MODEL.md`](./DATA_MODEL.md). Stale references (Pinecone, Lambda/Mangum, Atlas, "SDS", 1200×1200) have been corrected inline below.

## What It Is

A web application that ingests a company's brand assets — voice guidelines, tone documents, past LinkedIn posts, content pillars, color palette, typography — and uses that corpus to generate on-brand social content. Generated content renders as designed LinkedIn image cards and text posts, ready to download and publish. Built as a portfolio piece, using a fictional demo brand — **Verdure Materials** — as the primary demo corpus (drafted in [`demo-corpus/`](./demo-corpus/)).

---

## Why RAG

RAG (Retrieval Augmented Generation) is the right pattern because:

- Brand guidelines and past content are too large to fit in a single context window
- The corpus needs to persist between sessions and grow over time
- Content needs to be informed by semantically relevant brand context retrieved at query time — not just a one-sentence instruction
- Generic content generation is prompt → response. On-brand content generation requires retrieval. That retrieval step is the differentiator.

---

## AI Pattern

**RAG — Retrieval Augmented Generation**

The middle tier between basic prompt → response and tool use / function calling. Brand assets are chunked, embedded into vectors, stored in a vector store behind a swappable interface (**Chroma** in local dev, shared **Qdrant** in production), and retrieved at query time to inform content generation. Claude handles content generation using the retrieved brand context.

---

## Phase 1 — Templates (build first)

- Brand workspace — upload and ingest brand assets (PDFs, text, past posts)
- Per-workspace vector isolation — each workspace's content is separate (Chroma collection in dev / Qdrant payload-filtered namespace in prod)
- LinkedIn text post generation — informed by ingested brand corpus
- LinkedIn image card generation — designed card with:
  - 2-3 pre-designed card layouts built as React components
  - Claude generates copy and places it into the chosen template automatically
  - Brand colors, typography, and logo applied from workspace profile
  - Unsplash API for keyword-based stock photo search
  - User file upload for custom images
  - PNG export via Satori (HTML→SVG) + @resvg/resvg-wasm (SVG→PNG) — one definition drives both preview and export
- Content history — saved generations per workspace

---

## Phase 1.5 — Basic Customization (after Phase 1 is working)

- Layout picker — user chooses between the 2-3 pre-built templates
- Image swap — cycle through Unsplash results or re-upload without regenerating copy
- Inline text editing — user can tweak generated copy directly in the card preview before exporting
- Accent color toggle — switch between colors within the brand palette

---

## Phase 2 — Document Output (after Phase 1.5 is working)

- Word document output — branded `.docx` files via python-docx (case studies, one-pagers, proposals)
- PowerPoint output — branded `.pptx` files via python-pptx (pitch decks, content presentations)
- PDF export — alongside Word output, preserves formatting across devices

---

## Design Phase — Complete

All screens designed and approved using Claude Design (Folio design system). Design files exist as HTML reference artifacts in [`mocks/`](./mocks/). The full design system is documented in [`DESIGN.md`](./DESIGN.md).

**Approved screens (10 total):**

| Screen | File | Notes |
|---|---|---|
| Landing page | Folio_Landing_dc.html | Public marketing page |
| Login | Folio_Login___Settings_dc.html | Includes demo access path |
| Workspace Setup (4 steps) | Folio_Workspace_Setup_dc.html | Onboarding flow |
| Dashboard | Folio_Dashboard_dc.html | App home base |
| Generate | Folio_Generate_dc.html | Primary working screen |
| Content History | Folio_History___Assets_dc.html | Generation archive |
| Asset Manager | Folio_History___Assets_dc.html | Brand corpus management |
| Settings | Folio_Login___Settings_dc.html | Profile, workspace, notifications |

**Confirmed design decisions:**
- Identity: "Folio" — Plus Jakarta Sans + DM Mono, studio white (`#F8F9FA`), magenta accent (`#C2185B`)
- All ten screens are consistent — zero design drift across the full product
- Demo workspace: "Verdure Materials" (eco/sustainability brand, forest green `#1C3A2E`)
- Login page includes "Explore as demo user" path — no credentials required for portfolio visitors

**Tailwind config token values (use these when setting up the project):**

```ts
// tailwind.config.ts — theme.extend.colors
colors: {
  background: '#F8F9FA',
  surface: '#FFFFFF',
  'surface-variant': '#F1F3F5',
  foreground: '#1A1D21',
  'muted-foreground': '#6C737A',
  border: '#E4E7EA',
  preview: '#E8EAED',
  accent: {
    DEFAULT: '#C2185B',
    strong: '#9E1248',
    soft: 'rgba(194,24,91,0.10)',
    ring: 'rgba(194,24,91,0.34)',
    foreground: '#FFFFFF',
  },
  success: '#15803D',
  warning: '#B45309',
  destructive: '#B42318',
}
```

**Google Fonts (preload these two only):**
```
Plus Jakarta Sans: wght@400;500;600;700
DM Mono: wght@400;500
```

---

## Design Scope

- Public marketing landing page — built in React + Vite, itself a portfolio piece
- Onboarding flow — workspace setup and asset upload UI
- Workspace dashboard — asset management, content history
- LinkedIn image card renderer — the primary designed output component
- Social card preview with Unsplash search + user upload image selection
- Light-first UI with dark mode as a secondary option
- PNG export functionality for finished cards

---

## Design Identity

**App type:** B2B creative productivity tool — closer to Figma, Linear, or Framer than an enterprise console.

**Visual identity:** Own identity, completely independent from any client brand. The app is a neutral container for any company's brand assets — the UI should never compete with the content being created inside it.

**Mode:** Light-first. Users are making visual decisions — choosing images, reviewing copy, evaluating colors. Light mode is better for color accuracy and visual judgment. Dark mode supported as a secondary preference.

**Reference apps:** Linear, Framer, Craft, Notion — polished and professional with warmth, not cold enterprise dashboards.

**Card preview:** The designed card output is the hero of the Generate page. All surrounding UI should step back and frame it like a canvas — contained panel with a defined border, clearly separated from the app chrome.

---

## Tech Stack

### Frontend
- React + Vite (breaking away from Vue for portfolio diversification — SSR not required for this app)
- Tailwind CSS (design-forward, full visual control)
- TypeScript
- Satori + @resvg/resvg-wasm (card to PNG export — deterministic, preview == export)

### Backend
- FastAPI (Python) — runs on ECS Fargate in production (not Lambda/Mangum; cold starts degrade SSE streaming)
- Motor (async MongoDB driver) + Pydantic v2; python-jose for JWT auth
- Hand-rolled RAG pipeline (OpenAI + Anthropic SDKs + the Chroma/Qdrant client directly); only the standalone `langchain-text-splitters` for chunking — not the full LangChain framework
- pdfplumber (pypdf fallback) for parsing uploaded PDF brand guidelines
- python-docx (Word output — Phase 2)
- python-pptx (PowerPoint output — Phase 2)

### Databases
- MongoDB — workspaces, content history (Docker locally for dev; shared self-hosted instance in production — not Atlas)
- Vector store behind a swappable interface — Chroma locally for dev, shared Qdrant in production; per-workspace isolation

### AI
- Anthropic Claude API (claude-sonnet-4-6) — content generation + Unsplash keyword suggestion
- OpenAI text-embedding-3-small — document embedding (Anthropic does not offer embedding models)

### Image
- Unsplash API — free, keyword-based stock photo search
- User file upload — direct image upload stored in S3

### File Storage
- AWS S3 — brand asset files and uploaded images

---

## AWS Deployment

Brand Content Studio deploys into the shared AWS infrastructure platform described in `aws_infrastructure_plan.md`. See that document for the full architecture.

**Project-specific deployment:**
- Frontend: S3 + CloudFront
- Backend: FastAPI on ECS Fargate (shared cluster, own service)
- File storage: S3 (project-specific bucket)
- Vector database: Shared Qdrant ECS task (own collection: `brand-content-studio`)
- App database: Shared MongoDB instance (own database: `brand_content`)
- Secrets: AWS Secrets Manager (namespaced `brand-content-studio/*`)

**Resource tags — apply to every AWS resource:**
- `project: brand-content-studio`
- `env: production`

---

## Estimated Monthly Cost (Portfolio Scale)

| Service | Cost |
|---|---|
| Anthropic Claude API | ~$5-10/month |
| OpenAI Embeddings | ~$1-2/month |
| Shared Qdrant ECS task (split across RAG projects) | ~$5-8/month share |
| Shared MongoDB instance (split across projects) | ~$3-5/month share |
| Unsplash API | $0 (free tier) |
| AWS S3 + CloudFront | ~$0 at portfolio traffic |
| **Total** | **~$15-25/month** |

---

## Auth

Lightweight JWT (python-jose), reusing the Employee Management System auth pattern, with a **seeded demo user** and an **"Explore as demo"** bypass button. No public sign-up — this is a portfolio piece, not a multi-user product.

---

## Where This Fits in the Portfolio AI Progression

| Project | AI Pattern | Status |
|---|---|---|
| Smart Resume Builder | Prompt → Response | In progress |
| Brand Content Studio | RAG | Design complete — ready to build |
| EMS AI Chatbot | Tool Use / Function Calling | Planned addition to existing Employee Management System |

---

## LinkedIn Card Design Reference

The target output is a designed **1080×1350 (4:5 portrait)** card — LinkedIn's best-performing feed image ratio — with:
- Logo placement top left
- Eyebrow label (category/topic in small caps)
- Large headline with brand accent color highlights
- Brand-specified body font
- Footer with CTA and hashtag
- Image sourced from Unsplash API or user upload
- Exported as PNG ready to upload to LinkedIn

> The approved mocks define **three card archetypes** — photo-led, statement, and quote (see [`DESIGN.md`](./DESIGN.md) and the mocks in [`mocks/`](./mocks/)). These supersede the single "split layout" originally sketched here.

---

## Page Map

### Public
**Landing page** — markets the app and drives sign-in. The portfolio piece itself, needs to look sharp.
- Hero with card preview, feature sections, sign in CTA

### Auth
**Login** — entry point from the landing page. Two paths: a prominent "Explore as demo user" button that bypasses auth and loads the Verdure Materials demo workspace, and a standard email/password sign-in form below a divider. No sign-up flow needed for a portfolio demo.
- Demo access button (primary for portfolio visitors), email input, password input, forgot password link, sign in button

### Onboarding (one-time)
**Workspace setup** — first-time experience. Collects brand assets and profile before the user can generate anything.
- Workspace name input, brand asset uploader, logo upload, color palette picker, typography selector, progress stepper

### Core App
**Dashboard** — home base. Overview of the workspace and entry point to all actions.
- Recent generations, asset summary, generate new button, side nav

**Generate** — the primary working screen. Most complex page in the app. Where the user creates content and previews the output.
- Topic / brief input, output type selector, template picker, live card preview, Unsplash image search, image upload, inline text editor, export / download

**Content history** — all past generations in one place. Re-open, re-export, or use as a starting point.
- Card grid, filter by type (All / Image cards / Text posts), generation count, re-open / re-export actions

**Asset manager** — view and manage the ingested brand corpus. Add new documents as the brand evolves.
- Corpus status bar, ingested asset list with file type / name / status columns, compact upload zone, empty state

**Settings** — profile, workspace management, and notification preferences. The quietest page in the app.
- Read-only profile fields with Edit button, workspace name input, danger zone (delete workspace), notification toggles

---

## Important Considerations

### Before Writing Any Code

**Demo data preparation — highest priority**
The RAG layer is only as impressive as what you feed it. A thin corpus produces generic output that doesn't demonstrate RAG value. Before building, prepare a rich set of **Verdure Materials** brand assets (already drafted in [`demo-corpus/`](./demo-corpus/)):
- Detailed voice and tone guidelines
- 10-15 past LinkedIn posts
- Content pillars and audience personas
- Competitor analysis
- Brand color palette and typography specs

The demo lives or dies on the quality of this corpus.

**LinkedIn card dimensions**
Build the card React component at exactly **1080×1350 px (4:5 portrait)** from the start — LinkedIn's best-performing feed image ratio. Retrofitting dimensions after the fact is painful and will affect how the PNG exports render when uploaded.

### During Development

**Unsplash attribution requirement**
Unsplash's free API license requires displaying "Photo by [name] on Unsplash" somewhere visible — either on the card itself or in the UI near the image. Design for this from the start, not as an afterthought.

**Stream the copy generation**
Generate and stream Claude's copy token by token into the card preview as it's being written rather than waiting for the full response. Significantly more impressive in a demo — makes the AI feel alive rather than a loading spinner. Build this from the start.

**Retrieval evaluation / debug panel**
Build a simple debug panel during development that shows which brand asset chunks were retrieved for a given generation. Without visibility into what's being retrieved you're flying blind on whether the RAG pipeline is actually working correctly.

### Phase 2 Addition

**PDF alongside Word**
When building document output in Phase 2, add PDF export alongside `.docx` — PDF preserves formatting across devices and is often more useful for sharing. Add it in the same phase rather than treating it separately.

---

## Build Phase — Starting Point

Design is complete. When opening a new chat to start the build, paste this spec plus the sibling docs ([`DECISIONS.md`](./DECISIONS.md), [`ARCHITECTURE.md`](./ARCHITECTURE.md), [`DATA_MODEL.md`](./DATA_MODEL.md), [`PLAN.md`](./PLAN.md), [`DESIGN.md`](./DESIGN.md)). The **canonical phased build sequence lives in [`PLAN.md`](./PLAN.md)** (Phase 0 scaffold → 1a text posts → 1b image cards → 1.5 → 2 → deferred deploy); the high-level order below is consistent with it:

1. **Project setup** — React + Vite + TypeScript + Tailwind, paste the token values from the Design Phase section above into `tailwind.config.ts`, install Lucide React, set up the folder structure
2. **FastAPI backend** — skeleton with health check, CORS, config via `.env` locally (AWS Secrets Manager in production)
3. **Auth** — JWT (python-jose), seeded demo user, the "Explore as demo user" bypass route
4. **Workspace setup flow** — file upload (local FS in dev / S3 in prod), hand-rolled ingestion pipeline (chunk → embed → upsert), vector namespace creation (Chroma collection / Qdrant namespace)
5. **Generate page** — the core product. RAG retrieval, Claude streaming, card preview component, Unsplash integration, PNG export
6. **Dashboard** — reads from MongoDB, recent generations grid
7. **Content History + Asset Manager** — CRUD on existing data, simpler than Generate
8. **Settings** — profile display, workspace name update, notification toggles
9. **Landing page** — last, once the app works. Static React, no backend needed.

---

## Key Notes

- Anthropic does not offer embedding models — use OpenAI text-embedding-3-small for embeddings, Claude for generation
- Adobe Firefly API has ~$1,000/month enterprise minimum — not suitable for portfolio scale. Use Unsplash API + user upload instead
- Build Phase 1 (templates) first, then Phase 1.5 (basic customization), then Phase 2 (Word, PowerPoint, and PDF)
- React + Vite chosen over Next.js — SSR is not required for this app, no justification for the added complexity
- The landing page itself is a portfolio piece — treat it as such
- Template design time is likely the most underestimated part of the build — plan for it accordingly
