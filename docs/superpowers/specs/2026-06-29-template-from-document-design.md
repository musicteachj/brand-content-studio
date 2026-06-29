# Fill a Branded Template from an Uploaded Document — Design

**Goal:** Let a user take an **unbranded / minimally-styled** document (`.docx`/`.pptx`/`.pdf`/`.txt`/`.md`), upload it onto one of their **branded templates**, and get the document's *content* mapped into the template's `{{placeholders}}` — producing a branded, on-layout document. "Bring a rough draft, get back the official branded version."

**Non-goals (v1):** Structure-preserving output (repeatable template regions); persisting the source document; a separate page or new collection; changing how templates are authored or how rendering works. Author-written placeholder **hints** are a documented fast-follow, not v1.

## Background (what already exists — Phase 5)

- Templates: a user uploads a **branded** `.docx`/`.pptx` with `{{placeholders}}`. `template_service.discover_placeholders(data, fmt)` finds the tags; `clamp_values` + `render(data, values, fmt)` fill and render (template styling is authoritative — DECISIONS #24).
- AI-fill: `POST /workspaces/{id}/templates/{template_id}/ai-fill` drafts a value per placeholder **from a typed `brief`**, via `template_fill.build_fill_tool(placeholders)` + `GenerationService.fill_template_values(system, user, tool)` + `clamp_values`. Generative, **demo-allowed**, nothing persisted. Returns `TemplateAiFillResponse { values }`.
- Content extraction: `rag/loaders.py` handles **PDF + Markdown/text only**. **No `.docx`/`.pptx` content extraction exists.**

This feature = **AI-fill, but sourced from an uploaded document instead of a typed brief** — fixed-slots-condense fidelity: content is mapped/summarized into whatever placeholders the template has (the template layout is authoritative), and the user reviews/edits the draft values before rendering.

## Design

### 1. Content extraction — new `app/services/content_extraction.py`

`extract_document_text(data: bytes, filename: str) -> str`: returns a bounded, lightly-structured plain-text representation of the source.
- `.docx` → **python-docx** (already a dependency): paragraphs in order; prefix heading-styled paragraphs and list items so structure survives as text (e.g. `# Heading`, `- bullet`).
- `.pptx` → **python-pptx** (already a dependency): per-slide, the text of each shape/table cell (`Slide N:` prefixes).
- `.pdf` → **pdfplumber** (already a dependency; reuse the loader's extraction).
- `.txt` / `.md` → decode as text (the `rag/loaders` text path already does this).
- **Safety (reuse Phase 6 ingestion pattern):** parse runs off the event loop (`asyncio.to_thread`) under a timeout; output is truncated to a model-safe budget (`MAX_SOURCE_CHARS = 40000`, ≈ 10–12 pages / ~10k input tokens — generous for a realistic multi-page doc while bounding latency/cost; the Anthropic console hard cap bounds total spend per DECISIONS #17); empty/garbage → a clear error.

This is distinct from `rag/loaders.load_sections` (which yields `Section`s for chunking) — extraction here yields one readable blob for the prompt. Kept in its own module (one responsibility).

### 2. AI mapping (reuses Phase 5)

- Reuse `template_fill.build_fill_tool(placeholders)` (strict tool built from the template's own placeholder names) and `build_fill_system()`.
- **New** `template_fill.build_fill_user_from_content(content: str, placeholders: list[str]) -> str` — the sibling of `build_fill_user(brief, placeholders)`, instructing the model to map the source **content** onto the placeholders, condensing to fit and leaving a placeholder empty when the source has nothing for it.
- Reuse `GenerationService.fill_template_values(system, user, tool)` and `template_service.clamp_values`.

### 3. Route — new `POST /workspaces/{id}/templates/{template_id}/fill-from-document`

Multipart `file: UploadFile`. Flow: load template (`get_template`, 404 if missing) → validate file type/size → `extract_document_text` → `build_fill_user_from_content` → `fill_template_values` → `clamp_values` → return `TemplateAiFillResponse { values }` (same shape as `ai-fill`, so the **review + render path is unchanged**). Generative + nothing persisted → **demo-allowed** (no `require_not_demo`), consistent with `ai-fill`. Ownership via `get_workspace_or_404`.

### 4. Client

On the template fill UI (in `features/templates/`), add a third content source next to "fill manually" / "draft from a brief": **"Fill from a document"** — a file upload (`.docx`/`.pptx`/`.pdf`/`.txt`/`.md`). On select it calls the new route and drops the returned `values` into the **same editable review fields**, then the existing Render/Download. A short note clarifies that content is *mapped and condensed to fit the template*.

### 5. Scope guards

Source ≤ 10 MB; extension allowlist `.docx`/`.pptx`/`.pdf`/`.txt`/`.md` (→ 415 otherwise); empty file → 400; extracted text truncated to `MAX_SOURCE_CHARS`; existing `MAX_PLACEHOLDERS` (40) / `MAX_VALUE_LEN` (2000) clamps still apply. No new Mongo collection, no new storage — the source is processed in-memory and discarded; the rendered output stays an ephemeral download.

## Error / edge handling

- Unsupported type → 415; empty → 400; oversized → 413; parse timeout/garbage → a friendly error surfaced in the UI (the user can still fill manually).
- Template with **no placeholders** → returns `{ values: {} }` (same as `ai-fill`) — nothing to map.
- More source content than slots → condensed to fit (visible in the review fields, editable before render).
- Demo user → allowed (generative); cross-owner template → 404.

## Testing

- **Server:** `content_extraction` unit tests — a tiny generated `.docx` and `.pptx` (python-docx/python-pptx) extract their text; truncation cap honored; unsupported type raises. Route test — `fill-from-document` returns mapped `values` (with `GenerationService` faked, like the existing template tests), 415 on bad type, 404 on missing template, allowed for demo.
- **Client:** the fill UI calls the new route on upload and populates the review fields (hook/component test mirroring the existing template tests).

## Out of scope / fast-follow

- **Placeholder hints** — let template authors attach a short hint per placeholder (stored on the template, fed into the fill prompt) to sharpen mapping on generically-named templates. The single highest-leverage quality follow-up.
- **Structure-preserving (ii)** — docx repeatable regions (`{% for %}`) so the output grows to match the source's section count.
- Mapping into logos/brand images (the template already owns those).
