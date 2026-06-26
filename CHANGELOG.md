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
| `0.5.0` | Phase 3 — "LinkedIn Post" objective (caption + card) |
| `0.6.0` | Phase 4 — brand setup & learning *(planned)* |
| `0.7.0` | Phase 5 — on-brand templates *(planned)* |
| `0.8.0` | Phase 6 — robustness & limits *(planned)* |
| `1.0.0` | first public deploy |

Git tags (`v0.0.0`, …) are created when a phase merges to `main` (see [`docs/WORKFLOW.md`](./docs/WORKFLOW.md) §7).

## [Unreleased]

### Added — Phase 4: Brand setup & learning — `0.6.0` *(PR-A: slices 4a + 4b)*

Make the app genuinely **multi-brand and editable in-app**: switch between workspaces from the top bar, manage them, and edit a workspace's whole brand identity (palette, fonts, voice, accent, logo) from Settings — no more single auto-selected seed. Implements slices 4a + 4b of [`docs/phase-4-plan.md`](./docs/phase-4-plan.md); see [`docs/DECISIONS.md`](./docs/DECISIONS.md) (#23). The backend was already multi-tenant, so this is reuse-heavy; **slice 4c (vision brand-learning) lands in PR-B.**

- **Workspace switcher + management (4a, client-only)** — a **TopBar dropdown** (`WorkspaceSwitcher` over a new Folio `dropdown-menu` Radix wrapper) lists the owner's workspaces with an active check, switches the active one (persisted in `stores/workspace`), and routes to **New workspace** (the existing `/setup` stepper) and **Manage workspaces**. A new Settings → **Workspaces** section lists workspaces with inline **rename** and **delete** (confirm dialog, keeps ≥1). `useActiveWorkspace` already let the persisted `activeId` win over the first-load fallback, so an explicit switch survives reload (clarified + test-pinned). New `useUpdateWorkspace` / `useDeleteWorkspace` mutations reuse the existing `routes/workspaces.py` CRUD — **no new server endpoints**.
- **In-app brand editor (4b, client)** — the Settings brand-identity card is read-only by default with an **Edit** affordance that reveals a `react-hook-form` + `zod` form (the first house form): **palette CRUD** (name + hex + color-picker + role), **fonts** (heading/body/mono), **voice summary**, and **accent-from-palette** (validated against the palette). Save sends the **full** `brand_profile` (the PATCH replaces it whole) via `useUpdateWorkspace`. Pure mapping/schema live in `brandIdentity.ts` (testable, fast-refresh-clean).
- **Logo upload (4b, server + client)** — implements the modeled-but-unused **`POST` / `DELETE /workspaces/{id}/logo`**, mirroring the card-image upload defenses (allow-listed JPG/PNG/WebP, 8 MB cap, server-derived key) and persisting via a **targeted** `brand_profile.logo` `$set`/`$unset` (never clobbers the rest of the profile); the existing image route serves it. The editor uploads/previews/removes the logo (saves immediately, separate from the field Save), previewing through the auth-gated `fetchImageDataUrl`. Made `resolve_image_content_type` public for reuse.
- **Demo guard, reconciled** — every workspace/brand/logo mutation stays `require_not_demo`-blocked server-side, and the UI **disables** create/rename/delete/edit for `is_demo` users so client and server agree.
- **Tests** — pytest (+6, 49 total): logo upload sets `brand_profile.logo` (palette untouched, bytes stored under the server-derived key), rejects bad type (415) / oversize (413) / empty (400), is **demo-blocked (403)**, and delete unsets the logo + removes the stored bytes. Vitest (+10, 37 total): `useActiveWorkspace` resolution (auto-select first + persist, honor a persisted id, recover from a stale id, `hasNone`), and the brand-profile mapping/schema (null↔'' round-trip, logo preserved, blank→null normalization, accent-not-in-palette + malformed-hex rejection).

### Added — Phase 3: "LinkedIn Post" objective — `0.5.0`

The first **objective** (vs. a raw format): one brief yields a full LinkedIn **post caption** *and* a matching **card**, built together from one retrieval — so the user gets something to post plus the copy to post with it. Implements Phase 3 of [`docs/phase-3-plan.md`](./docs/phase-3-plan.md); see [`docs/DECISIONS.md`](./docs/DECISIONS.md) (#22). Built almost entirely from existing seams.

- **`/generate/post` SSE** — one hybrid retrieval, then: (1) **stream the caption** as a full LinkedIn post for the live typing effect (reuses `prompts/text_post.py` + `stream_text`); (2) **distill the matching card from that finished caption** via a forced, strict Anthropic tool-use call (reuses `image_card.CARD_FIELDS_TOOL`) — the card is the post's *hook*, compressed, not a copy. Same `{text} → {meta} → [DONE]` frame shape, same empty-corpus block, same `<brand_context>` defense; the distill step operates on the model's own caption (no new injection surface).
- **`type:"post_pack"` on generations** — `output` = the caption (`post_text`/`hashtags`/`char_count`, the `TextOutput` shape) plus the matching card **nested** under `output.card` (the `CardOutput` shape). No new collection; history, retrieval snapshot, and ownership come for free.
- **Image attach + customization route into the nested card** — the existing `PATCH /generations/{id}` now takes a `nested_key`: a `post_pack` merges `image`/`template_id`/`fields`/`accent_hex` into `output.card` (a `card` still merges at the top). Parallel Unsplash/upload image selection, the per-card accent palette guard, and "no `/generate` on customization" all carry over unchanged.
- **Client — new "LinkedIn post" Generate mode** (first in the toggle). A combined preview: the **card** (reuses `CardPreview` / `cardElement` / `useCardExport`) beside the **editable caption** (`PostCaptionPanel` — streams live, then a paste-ready textarea with Copy). Parallel image pick via the existing `ImagePickerPanel`. `usePostPackGeneration` mirrors `useCardGeneration` with caption semantics. History gains a **LinkedIn** filter; a post_pack shows the card thumbnail + caption snippet, and the detail dialog offers Customize (re-opens in post mode), Download PNG, and Copy caption.
- **Tests** — pytest (+4, 43 total): `/generate/post` streams the caption then distills + persists the nested card (image null until PATCH), empty corpus blocks Claude, and PATCH attaches an image into `output.card` (not top-level) with the accent guard holding for post_pack. Vitest (+2, 27 total): `usePostPackGeneration` hydrates a re-opened post_pack and an image selection **PATCHes the generation, never calls `/generate`**.

### Added — Phase 2: Document output — `0.4.0`

Turn a one-line brief into a **client-ready, on-brand document** — a branded `.docx` + a matching PDF (one-pager) or a `.pptx` (short deck), in the workspace's own colors and fonts — without opening Word or touching a color picker. The same RAG engine as text/cards pointed at a third, structurally richer medium: the studio writes and brands; the user briefs and downloads. Implements Phase 2 of [`docs/PLAN.md`](./docs/PLAN.md); see [`docs/phase-2-plan.md`](./docs/phase-2-plan.md) and [`docs/DECISIONS.md`](./docs/DECISIONS.md) (#21).

- **One shared `DocumentModel` → every format, rendered independently** — a typed model (title/eyebrow/lede/sections/footer) renders to `.docx` (**python-docx**), PDF (**ReportLab**), and `.pptx` (**python-pptx**) from one source of truth, so the formats match by construction. **No docx→PDF conversion, no LibreOffice/soffice, no headless browser** — pure-Python, clean for ECS, and (deliberately) no converter shell-out to add an injection/SSRF surface. The model is length/count-clamped server-side so a runaway response can't balloon a file.
- **Two archetypes** — **one-pager** (drives `.docx` + PDF) and **short-deck** (title slide → content slides → closing, drives `.pptx`), mirroring the 3-card pattern.
- **`/generate/document` SSE** — streams the draft as prose for the live preview, then resolves the typed `DocumentModel` via a forced, **strict Anthropic tool-use** call (never parsed from the stream), builds + stores the branded files, and emits the per-format storage keys in the terminal `{meta}`. Same `{text} → {meta} → [DONE]` shape, same hybrid retrieval, same empty-corpus block, same `<brand_context>` data-not-instructions defense as Phases 1a/1b.
- **`type:"document"` on generations** — no new collection; history, retrieval snapshot, and ownership come for free. Files persist through `StorageBackend` under a `documents/` prefix; an **auth-gated, ownership-scoped download route** (`GET …/generations/{id}/download/{fmt}`) rebuilds the storage key server-side (never trusts the stored value), `Content-Disposition: attachment`. Files are built **before** the generation is persisted, so a render failure can't leave a "complete" doc with no files.
- **Brand fonts** — the PDF embeds the real brand TTF when one is bundled in `brand_fonts_dir` (Verdure's DM Serif Display + Spectral ship in `server/app/assets/fonts/`, OFL); `.docx`/`.pptx` reference the font by name. **No runtime font fetch** (no SSRF surface); missing fonts fall back to a serif/sans base.
- **Client — third Generate mode (Text / Card / Document)** — reuses the brief box + retrieval debug panel. `DocumentArtifact` renders an archetype in its own shape: the one-pager as branded **"paper"** (`DocumentPage`), the short-deck as a stack of branded 16:9 **slide cards** (`DeckPreview`) — both in workspace colors/fonts, mirroring the generated file (never Folio chrome, DESIGN §7). A **multi-format download row** pulls each pre-rendered file through the auth-gated route as a blob with **no model call**. History gains a Documents filter, a compact thumbnail, and the same download row on grid cards + the detail dialog.
- **Tests** — pytest (+8, 39 total): python-docx **style assertions** (title = brand heading font + primary brand color, no app fonts) on a built `.docx`; the `.pptx` is a branded deck (slide count, brand font + color); PDF is valid; `build_document_output` clamps a runaway model; `/generate/document` persists `type:"document"` + builds both formats; empty corpus blocks Claude; the download route is ownership-scoped and rejects unknown formats/ids. Vitest (+4, 25 total): `DocumentPage`/`DeckPreview` render workspace fonts + primary color (never Folio); re-download hits the **download route, never `/generate`**.
- **Deps** — server `python-docx`, `reportlab`, `python-pptx`.

### Added — Phase 1.5: Customization — `0.3.0`

Make a generated card editable after the fact — change the copy, swap the layout, swap the image, pick the accent — and re-export **without ever re-calling Claude**. The model wrote the card once; customization is a client-side design loop. Implements Phase 1.5 of [`docs/PLAN.md`](./docs/PLAN.md); resolves the two open questions in [`docs/DECISIONS.md`](./docs/DECISIONS.md) (#20).

- **Contract (one change)** — `accent_hex` added to `CardOutput` + `GenerationUpdate` (hex-shape validated in the model; **palette membership** enforced in the PATCH route against the workspace's own brand colors, so a card accent is always on-brand). The existing `PATCH /generations/{id}` already merged partial `output`; it now carries layout, inline fields, and the accent. PATCH stays allowed for the demo user (their own generations); only delete/asset/workspace mutations are `is_demo`-guarded.
- **Layout swap, no regenerate** — re-render the same `output.fields` in a different archetype via the editor + `TemplatePicker` (now reused post-generation); `PATCH template_id`. Copy is preserved; **no `/generate` call**.
- **Per-card accent** — a brand-palette swatch picker on the recessed *Customize* panel sets `output.accent_hex`; `cardColors()` threads a per-card override that wins over the workspace tint and re-renders the card client-side.
- **Inline text editing on the card** — an *Edit text* toggle swaps the locked Satori image for the live DOM card with `contentEditable` fields, wired through the **same** `buildCardElement` (the `edit` handler path is DOM-only, never Satori), so preview == export still holds. Edits are a local **draft**, ephemeral until an explicit **Save** (PATCH only the changed keys) with **Discard**; long/edited/swapped headlines **auto-fit** the fixed 1080×1350 bounds via a deterministic `fitTextSize` scaler (identical in preview and export).
- **Workspace brand-color UI tint** — resolved as a **Settings toggle, default on** (`useAppearance` → `applyAccentTint` overrides `--accent`/`--accent-strong`/`--ring`/`--accent-foreground` with the workspace primary). **Cosmetic only** — never touches semantic tokens (success/warning/destructive), DESIGN §7.
- **Settings page** — replaces the “Coming soon” stub: Theme (light/dark/system, the app's first dark-mode wiring), the brand-tint toggle, and a read-only brand-identity card (palette + fonts). Quiet, no account/destructive controls.
- **History → Customize** — a re-opened card **hydrates** into the same Generate editor (ephemeral `useGenerateStore` hand-off + `useCardGeneration.loadGeneration`, no model call), so layout/accent/copy edits **and image swap** work on saved cards, not just the live session.
- **Tests** — pytest: PATCH updates `output.fields`, swaps `template_id` keeping copy, accepts a palette accent, rejects non-palette + malformed hex, rejects text generations, rejects empty payloads (31 total, +7). Vitest: `fitTextSize` shrink/min/monotonic, per-card accent precedence in `cardColors`, in-place `contentEditable` rendering + `onEdit` emission, and `useCardEditor` save → **PATCH with only changed keys, asserted to make no `/generate` call** (20 total, +17).

### Added — Phase 1b: Image cards + PNG export (the design system) — `0.2.0`

Generate a designed 1080×1350 card in the workspace's brand and export it as a crisp PNG. Implements Phase 1b of [`docs/PLAN.md`](./docs/PLAN.md); resolves the Phase 1b open question in [`docs/DECISIONS.md`](./docs/DECISIONS.md) (#19).

- **`/generate/card` SSE** — streams natural card copy for the live typing effect (`{text}` deltas), then resolves the structured fields (`eyebrow/headline/body/cta/hashtag`) + `suggested_keywords` via a forced, **strict Anthropic tool-use** call — never parsed from the stream (ARCHITECTURE gotcha #8). Frame shapes mirror Phase 1a (`{text}` → terminal `{meta}` → `[DONE]`); same hybrid retrieval; empty corpus blocked before Claude is called. (`prompts/image_card.py`, `generation_service.stream_copy` + `extract_card_fields`, `routes/generate.py`.)
- **Unsplash proxy + upload** — `services/unsplash_service.py` (server-proxied search, key never reaches the client) normalizes mandatory attribution (UTM-tagged) onto every result and fires the **download-tracking** endpoint on selection (license requirement, gotcha #4); `routes/images.py` adds the global search/track surface plus workspace-scoped image upload (type/size-validated, server-derived keys) and an auth-gated serve route.
- **Three Satori archetypes** — PhotoLed · Statement · Quote, authored in Satori's CSS subset using **only** workspace fonts + colors (never Folio chrome, DESIGN §7). One shared element drives the live DOM preview, the locked Satori preview, and the resvg-wasm PNG export, so **preview == export by construction**. Brand fonts load as TTF buffers for Satori and as `@font-face` for the DOM from the same fontsource binaries.
- **Generate page (card mode)** — text/card mode toggle; a **guided in-place flow** (not a wizard): numbered step markers on the controls (`STEP 1 · TEMPLATE`, `STEP 2 · BRIEF`) and the two finishing actions (*Add an image*, *Export*) on the card itself, with the image step nudged in `accent` when the card is ready but bare. Explicit template picker (brand-colored thumbnails, no auto-select); `CardPreview` (drafting typing card → locked Satori preview → `useCardExport` 1080×1350 PNG); slide-in `ImagePickerPanel` (keyword-seeded Unsplash search that auto-fills when keywords arrive without clobbering a typed query, masonry grid with visible attribution, upload). Image selection is parallel — available while copy streams and surviving a regenerate; card generations persisted, image attached via `PATCH /generations/{id}`; Content History renders card thumbnails + a card detail view, with **Copy text** (posts) and **Download PNG** (cards) on **both the grid cards and the detail view** (via a shared `useGenerationActions` hook). The card download re-exports from the persisted `output` with **no model call** — the Phase 1.5 "re-export without re-calling Claude" goal, pulled forward into History.

### Fixed
- **Card thumbnail sizing** — the scaled-down card used a CSS `transform`, which doesn't shrink layout box size, so the un-scaled 1350px-tall element blew out the container (huge empty gap below each History card / detail dialog). The scaled card is now absolutely positioned and the box clipped, so its height comes purely from the 4:5 aspect ratio.
- **Missing-glyph (tofu) box in card copy** — the brand fonts load as the "latin" subset (no arrow/emoji/symbol glyphs), so a model-emitted `→` rendered as a tofu box. Glyphs outside the renderable ranges are now stripped at render time (`cleanGlyphs`, applied across preview/export/thumbnail; General Punctuation kept), and the prompt asks for plain-text, short CTAs.
- **Tests** — pytest: card route streams copy + persists fields/keywords, card empty-corpus block, Unsplash attribution normalization (httpx mocked), missing-key guard, and the download-tracking **SSRF guard** (rejects non-`api.unsplash.com` hosts) (24 total). Vitest: card archetypes render workspace fonts (computed `font-family`) never the app's, attribution renders when present (3).
- **Deps** — client `satori` + `@resvg/resvg-wasm` (lazy code-split), `jsdom` (test); server `UNSPLASH_ACCESS_KEY` (set it in `server/.env` for live Unsplash search).

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
