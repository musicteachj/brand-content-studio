# Phase 2 — Document output (slice plan)

> **Status: built + verified on `feat/2-documents`.** Both slices (2a docx+PDF one-pager, 2b pptx
> short-deck) landed on the one branch (2b layered on 2a's uncommitted work). Server gate (ruff + mypy +
> 39 pytest) and client gate (tsc + eslint + prettier + build + 25 vitest) green; **live acceptance run
> passed** (one-pager `.docx`+PDF and short-deck `.pptx` generated from a brief, downloaded with Verdure
> colors/fonts, re-download makes no `/generate` call). Tier-2 review gate done (`/code-review` high:
> 3 findings — render-after-persist + accent parity fixed, the 3rd folded in; `/security-review` full:
> clean). Pending: commit → push → PR into `dev`; phase boundary `dev → main` + tag `v0.4.0` (Tier 3,
> incl. owner-run `/code-review ultra`). Original plan split this into `feat/2-documents` + `feat/2-pptx`;
> since 2a stayed uncommitted, both shipped on `feat/2-documents` under one Phase-2 review + PR.
>
> Working plan for `v0.4.0`. Follows [PLAN.md](./PLAN.md) §"Phase 2", [WORKFLOW.md](./WORKFLOW.md) (vertical slices, contract-first,
> backend-first), [ARCHITECTURE.md](./ARCHITECTURE.md), [DATA_MODEL.md](./DATA_MODEL.md),
> [DESIGN.md](./DESIGN.md), and [DECISIONS.md](./DECISIONS.md). Resolves the six Phase 2 open questions.

## Goal

Turn a one-line brief into a **client-ready, on-brand document the user can download and send** —
a `.docx` + a matching PDF (later a `.pptx` deck) in the workspace's own colors and fonts — **without
ever opening Word or touching a color picker.** It's the same RAG engine (1a/1b) pointed at a third,
structurally richer output medium: the studio *writes and brands*; the user *briefs and downloads*.

**User ability:** pick *Document* mode → choose an archetype → type a brief → watch it draft live in the
brand → download finished files → re-download later from History **with no model re-call** (the 1.5
principle, carried forward). It is **not** a document editor — briefing in, branded file out.

**Acceptance (PLAN.md):** generate a branded one-pager `.docx` and a **matching PDF** from a brief,
downloaded with the workspace's colors and fonts applied; pytest python-docx style assertions confirm
the branded styles.

## Resolved decisions (confirmed with the owner)

1. **PDF strategy → one shared `DocumentModel` rendered independently per format (no docx→PDF
   conversion).** A `.docx` is built with **python-docx**, the PDF with **ReportLab** (pure-Python),
   the `.pptx` with **python-pptx** — all from the *same* structured model, so "matching" means *same
   content + same brand styling from one source of truth*, not a byte-identical render. **No
   LibreOffice/`soffice`, no WeasyPrint** — both are heavy system deps against the zero-local-dep /
   clean-ECS ethos, and a converter shell-out is the exact Tier-2 injection/SSRF surface we avoid.
   Bonus: the PDF is the *most* brand-faithful format because we **embed the real brand TTF**, whereas
   docx/pptx only reference the font by name and fall back if the opener lacks it.
2. **Archetypes → two, mirroring the 3-card pattern.** **One-Pager** (drives `.docx` + PDF; the
   acceptance target) and **Short Deck** (drives `.pptx`). One `DocumentModel` (typed sections) drives
   all formats — parity is structural, like "one Satori element → preview == export."
3. **Data model → extend `generations.type` with `"document"`; no new collection.** History, retrieval
   snapshot, PATCH, delete, and ownership all come for free. `output` holds the structured model + the
   per-format storage keys (see contract). Files go through `StorageBackend` under a `documents/`
   prefix; a new **auth-gated download route** mirrors `serve_image`.
4. **Generation flow → mirror cards.** Stream natural prose into a live preview (`{text}` deltas) for
   the demo "wow," then a **forced strict tool-use** call (`extract_document_sections`) for the typed
   `DocumentModel`, then **build the files server-side at stream end**, persist, and emit the format
   keys in the terminal `{meta}`. Same `{text} → {meta} → [DONE]` shape, same hybrid retrieval, same
   empty-corpus block, same `<brand_context>` injection-defense wrapper.
5. **Client surface → a third Generate mode (Text / Card / Document).** Reuses the brief box, retrieval
   debug panel, and history wiring. The card-preview hero is swapped for a **paginated document
   preview**; formats are a **download row** (`Download .docx` / `Download PDF`). History shows a
   doc-style thumbnail + a detail view with the same multi-format download row (extend
   `useGenerationActions`).
6. **Format scope → two slices.** **2a: `.docx` + PDF one-pager** end-to-end (hits the acceptance
   criterion + the python-docx pytest), PR'd first. **2b: `.pptx` Short Deck** follow-on, reusing the
   same `DocumentModel`.

## What already exists (reuse, do NOT rebuild)

- **Retrieval** — `services/retrieval_service.py` (hybrid: always voice_summary + pillars, then
  semantic top-k, workspace-scoped). Reuse the **same** step — that's the point of the phase.
- **Injection defense** — `prompts/{text_post,image_card}.py` wrap retrieved chunks in a delimited
  `<brand_context>` block framed as data-not-instructions. Mirror in `prompts/document.py`.
- **Generation** — `generation_service.py`: SSE `stream_copy` (typing effect) + forced strict tool-use
  `extract_card_fields`. Add a sibling `extract_document_sections`; reuse the streaming path verbatim.
- **Storage** — `StorageBackend` protocol + path-traversal-guarded local FS / S3, server-derived keys
  (`build_*_key`). Add `build_document_key(workspace_id, generation_id, fmt)`; never hand-roll writes.
- **Persistence/history** — `routes/generations.py` (list/get/delete/PATCH) + the discriminated
  `output` + retrieval snapshot. `type:"document"` slots in; no new collection.
- **Auth-gated download** — `routes/images.py::serve_image` (`get_workspace_or_404`, key rebuilt
  server-side, `Response`). Mirror for `GET …/generations/{gid}/download/{fmt}` with
  `Content-Disposition: attachment`.
- **Brand fonts** — fontsource binaries already fetched client-side for Satori. Add a small
  **server-side brand-font fetch/cache** (or bundle Verdure's DM Serif Display + Spectral) so ReportLab
  /python-docx embed the real TTF (see Risks).
- **Client** — `lib/sse.ts`, the Generate page mode toggle, the shared `useGenerationActions`
  (copy/download) hook, the Folio design system + design skills.

## Contract changes

**New deps** (`server/requirements.txt`): `python-docx`, `python-pptx`, `reportlab`.

**Models** (`server/app/models/generation.py`, mirrored in `client/src/types`):
- `GenerationType.document = "document"`.
- `DocumentArchetype` enum: `one_pager = "one-pager"`, `short_deck = "short-deck"`.
- `DocumentGenerateRequest{ brief, archetype, tone }`.
- The typed `DocumentModel` (the tool-use schema + persisted shape):
  ```jsonc
  { "archetype": "one-pager",
    "title": "…", "eyebrow": "…", "lede": "…",
    "sections": [ { "heading": "…", "body": "…", "bullets": ["…"] } ],  // bounded count/length
    "footer": "…" }
  ```
- `DocumentOutput{ model: DocumentModel, formats: { "<fmt>": { "storage_key": str } } }` on the
  generation `output` (discriminated by `type == "document"`). `formats` carries `docx` + `pdf` in 2a,
  adds `pptx` in 2b.

**Routes** (`server/app/routes/documents.py`, registered like `generate.py`):
- `POST …/generate/document` (SSE) — stream prose → tool-use → build files → persist → terminal
  `{meta}` with the generation id + retrieval payload + the format keys.
- `GET …/generations/{gid}/download/{fmt}` — auth-gated, ownership-checked, key rebuilt server-side,
  `Content-Disposition: attachment`, correct media type per format.

## Slice sequence (each: contract → backend+pytest → client → polish → self-review)

### Slice 2a — One-pager `.docx` + PDF  (`feat/2-documents`)
1. **Contract** — the models above (docx + pdf only); `python-docx` + `reportlab` to requirements.
2. **Backend** — `prompts/document.py` (one-pager system + `<brand_context>`); `extract_document_sections`
   tool; `services/document_service.py` with a `DocumentModel` → **DocxRenderer** + **PdfRenderer** (both
   read `brand_profile.colors`/`fonts`, embed the brand TTF); `routes/documents.py` SSE +
   `build_document_key` + the download route. Persist `type:"document"` with the retrieval snapshot.
3. **Client** — Document mode on Generate (reuse brief box + retrieval debug panel); paginated one-pager
   **DocumentPreview** in the brand (tokens, never hardcoded hex; brand fonts via the existing
   `@font-face` injector, never Folio chrome — DESIGN §7); a **format download row** wired to the
   download route; History doc thumbnail + detail download row via `useGenerationActions`.
4. **Polish** — streaming `aria-live`, empty-corpus block, loading/error states, reduced-motion.
   *Acceptance:* brief → branded one-pager `.docx` **and** matching PDF download, Verdure
   green/serif applied; re-download from History makes **no** `/generate` call.

### Slice 2b — Short-deck `.pptx`  (`feat/2-pptx`)
Add the `short-deck` archetype + a **PptxRenderer** from the same `DocumentModel`; archetype picker on
Document mode; `pptx` added to `formats` + the download row. *Acceptance:* brief → branded `.pptx`
deck (title + content slides) in brand colors/fonts.

## Tests

- **pytest (the backbone — PLAN.md):** python-docx **style assertions** confirm branded styles
  (heading font name/size, brand color on title/accents, section structure) on a built `.docx` from a
  fixed `DocumentModel`; `DocumentModel → renderer` is deterministic given fixed input (mock the model
  call); `/generate/document` SSE persists `type:"document"` + format keys (mock the Anthropic stream +
  tool-use); empty-corpus blocks generation (Claude not called); download route is ownership-scoped
  (no cross-workspace fetch) and rejects an unknown `fmt`; `storage_key` stays under the workspace
  prefix. 2b adds a python-pptx slide/style assertion.
- **vitest:** DocumentPreview renders **workspace** fonts (computed `font-family`), never the app's;
  re-download from History issues **no** `/generate` fetch (assert on the fetch mock).

## Risks / gotchas

- **Untrusted content in documents (Tier 2).** Retrieved brand chunks feed the prompt → keep the
  `<brand_context>` data-not-instructions framing. The model's own output is written into files; render
  it as **plain text into typed fields** (no HTML/template injection), and bound section count/length
  in the tool schema so a runaway response can't balloon a file.
- **No converter shell-out.** Choosing ReportLab over `soffice`/WeasyPrint deliberately removes the
  injection/SSRF surface a headless converter would add — cite this in the security review.
- **Brand-font embedding.** ReportLab needs the actual TTF (`pdfmetrics.registerFont`); python-docx sets
  the run font by name (graceful fallback if the opener lacks it). Fetch/cache the workspace fonts
  server-side (or bundle Verdure's). Confirm license to embed Google fonts (OFL — fine).
- **File-size / parse DoS.** Bound the model output (above) and cap built-file size; keep the PDF/doc
  build synchronous but fast (pure-Python, no browser).
- **Demo user.** Document **generation must stay allowed** for the demo user (their own generations);
  only delete/asset/workspace mutations are `is_demo`-guarded.

## Review gate

File generation + storage + new deps are **sensitive surfaces → Tier 2**: `/code-review` **high** +
`/security-review` **full** before the first push of each branch (untrusted-content-in-documents,
`storage_key` path traversal, the new deps, the download route's ownership scope). Fix every finding or
accept with a one-line reason in the PR. **No commit/push without explicit per-action approval.** Fold
any UI improvements back into DESIGN.md (DECISIONS #18). At phase end: update CHANGELOG `0.4.0` + add the
DECISIONS entry, then `dev → main` + tag **`v0.4.0`** (Tier 3, incl. owner-run `/code-review ultra`).
