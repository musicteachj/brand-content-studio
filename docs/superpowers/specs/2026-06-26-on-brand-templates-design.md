# On-brand document templates — design (Phase 5, PR-A)

## Context

Phase 2 generates branded documents **from scratch** — one shared `DocumentModel` rendered into
`.docx`/PDF/`.pptx` with `brand_profile` colors and fonts applied
(`server/app/services/document_service.py`). Phase 5 adds the inverse, faithful path the roadmap
promised (PLAN R4, DECISIONS #21/#3): let an owner **upload their own branded `.docx`/`.pptx`
template** and pour content into it, so the output carries the template's *exact* styling.

The owner's stated priority: **consistent styles and branding, not AI verbiage.** The common case is
"I have my own text; apply it to a branded template." So the template's styling is **authoritative**
— we swap only the text in the user's file and never touch its fonts, colors, layout, headers, or
slide masters. Optionally, the model can draft the placeholder values from a short brief, but that's
secondary and lightweight.

This is **PR-A** of Phase 5. **Custom card presets (PR-B)** is a separate, later slice.

## Decisions (owner-confirmed)

1. **Both `.docx` and `.pptx`**, in one PR, via a shared pipeline + two format-specific fill
   functions.
2. **Template styling is authoritative** — fill text only; **no `brand_profile` injection** (unlike
   Phase 2 from-scratch docs).
3. **Dynamic discover-then-fill** — parse each template's own `{{placeholder}}` tags on upload; at
   fill time build a strict tool schema from those exact names (AI path) or render a form field per
   name (manual path).
4. **Primary path = the user's own text** (manual form); **optional path = one AI tool-use call**
   that fills the same placeholders (editable before export). Both feed one identical render step.
5. **Its own "Templates" nav page**; templates are **not** Assets (Assets are the retrievable RAG
   corpus; templates are output scaffolds, never ingested).
6. **Renders are ephemeral** — returned as a file download, not stored or added to History. The
   *template* is the managed/persisted entity.

## Architecture

A standalone Templates subsystem, independent of the RAG/generate pipeline.

**Upload:** validate the file (`.docx`/`.pptx`, size cap) → **discover placeholders** → store the
file via `StorageBackend` → insert a `templates` doc with the placeholder list.

**Fill + render (one shared render, two value sources):**
- *Manual (primary):* the client shows a form with one field per placeholder; the user types values.
- *AI draft (optional):* a brief → one forced strict tool-use call whose schema is built from the
  template's placeholder names → returns a value per placeholder; the user edits before exporting.
- *Render:* `render(template_bytes, values, fmt)` swaps only the `{{tags}}` and returns the filled
  file bytes — `docx` via **docxtpl**, `pptx` via **python-pptx paragraph-level replace**. No styling
  is altered; nothing is persisted.

**`.pptx` fidelity caveat (documented in UI + spec):** PowerPoint splits text into runs arbitrarily,
so a tag may fragment across runs. We substitute at the **paragraph** level (join the paragraph's
runs, replace, write the result into the first run keeping its formatting, clear the rest). This
preserves the slide design/theme/layout; the one limitation is that a tag with *mixed inline
formatting within itself* collapses to its paragraph's first-run style. In practice tags sit in their
own placeholder text, so it's rarely visible. `.docx` (docxtpl) has no such caveat.

## Components

**Server**
- `models/template.py` — `TemplateResponse { id, workspace_id, name, format, storage_key,
  placeholders: list[str], created_at }`; `TemplateRenderRequest { values: dict[str,str] }`;
  `TemplateAiFillRequest { brief: str }`; `TemplateAiFillResponse { values: dict[str,str] }`.
- `services/template_service.py`:
  - `discover_placeholders(data: bytes, fmt: str) -> list[str]` — docx via docxtpl's
    `get_undeclared_template_variables()`; pptx by regex-scanning shape paragraphs
    (`\{\{\s*([\w.]+)\s*\}\}`). De-duped, order-preserved, capped at `MAX_PLACEHOLDERS = 40`.
  - `fill_docx(data, values) -> bytes` (docxtpl render), `fill_pptx(data, values) -> bytes`
    (paragraph-level replace), `render(data, values, fmt) -> bytes` dispatch.
  - `clamp_values(values, placeholders) -> dict` — keep only known keys, clamp each to
    `MAX_VALUE_LEN = 2000`, missing → "".
  - Mongo CRUD: `create_template`, `list_templates`, `get_template`, `delete_template`
    (workspace-scoped, mirrors `workspace_service`/`asset_service`).
- `prompts/template_fill.py` — `build_fill_tool(placeholders) -> dict` (a strict tool whose
  `properties` are the placeholder names, all string, all required); `build_fill_system()` /
  `build_fill_user(brief, placeholders, chunks?)`. AI fill reuses `GenerationService._tool_call`
  (or a thin `fill_template_values` method). Retrieval is optional and light (tone is secondary).
- `routes/templates.py` (mounted at `/api/workspaces/{workspace_id}/templates`):
  - `POST ""` (multipart upload) — validate, discover, store, insert. `require_not_demo`.
  - `GET ""` → `list[TemplateResponse]`.
  - `DELETE /{template_id}` — delete doc + stored file. `require_not_demo`.
  - `POST /{template_id}/ai-fill` (`TemplateAiFillRequest`) → `TemplateAiFillResponse` (tool-use;
    demo-allowed — generative, no mutation).
  - `POST /{template_id}/render` (`TemplateRenderRequest`) → the filled file as an attachment
    (`Content-Disposition`), correct media type. Storage key for the template is rebuilt server-side.
- `requirements.txt` — add `docxtpl` (it depends on python-docx + Jinja2, already compatible).
- `main.py` — mount the templates router; `workspace_service.delete_workspace` also drops the
  workspace's `templates` (+ their stored files) so deletion stays clean.

**Client**
- `api/templates.ts` — `useTemplates`, `useUploadTemplate`, `useDeleteTemplate`, `useAiFillTemplate`,
  and a `renderTemplate(...)` blob download (POST → blob, like the Phase 2 document download).
- `features/templates/TemplatesPage.tsx` — manager (upload + list with format/placeholder-count +
  delete) and a fill view: pick a template → a dynamic form (one field per placeholder) → "Draft
  with AI" (brief → populates the fields, editable) → **Download**. Demo: upload/delete disabled with
  the shared `DemoNotice`; empty state when none.
- Nav: add a "Templates" item to `SideNav`; route in `App.tsx`. Types in `types/index.ts`.

## Data model

`templates` collection (new): `{ _id, workspace_id, owner_id, name, format: "docx"|"pptx",
storage_key, placeholders: string[], created_at }`. Template files stored under a `templates/` prefix
via a new `build_template_key(workspace_id, template_id, filename)` (mirrors `build_image_key`).
Rendered outputs are **not** stored.

## Error handling

- Upload: empty (400), wrong type (415 — only `.docx`/`.pptx`), oversize (413, reuse a MB cap).
- Discover: a corrupt/unopenable file → 422 "couldn't read this template."
- `MAX_PLACEHOLDERS` exceeded → 422 (a runaway template).
- Render: unknown/extra value keys are dropped; missing placeholders render blank; values clamped.
- AI-fill: model/tool failure → 502 + retry; never blocks the manual path.
- All mutations `require_not_demo`; ownership via `get_workspace_or_404`; demo UI disables with a
  visible `DemoNotice`.

## Testing

- **pytest:** `discover_placeholders` finds the tags in a fixture `.docx` (built with python-docx)
  and a fixture `.pptx` (built with python-pptx), de-duped + capped; `fill_docx` swaps `{{tags}}`
  and **preserves a known paragraph's font/color/size**; `fill_pptx` swaps a tag fragmented across
  runs and preserves the slide/run styling; `clamp_values` drops unknown keys + clamps length;
  upload parses + stores + inserts (415 on `.txt`, 413 oversize, demo 403); `render` returns a valid,
  openable file with the values substituted; `ai-fill` builds the dynamic tool and returns values
  (LLM faked); delete removes the doc + file; everything ownership-scoped.
- **vitest:** the dynamic fill form renders one field per placeholder and submits the values map;
  "Draft with AI" populates the fields from a mocked response; upload/delete disabled for demo.

## Out of scope (YAGNI / deferred)

- **Custom card presets** — Phase 5 PR-B, separate slice.
- Style-extraction fallback for **untagged** templates (DECISIONS #21's "lighter fallback") — v1
  requires `{{placeholders}}`; an untagged template just downloads as-is.
- Persisting renders / a render History; conditional or looped Jinja logic in templates (only simple
  `{{var}}` substitution); PDF output from templates (the user's template is docx/pptx).

## Verification

Stack: `docker-compose up` + server (`env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m
uvicorn app.main:app --port 8000`) + `npm run dev`. Live: on the Templates page, upload a branded
`.docx` with a couple of `{{tags}}` → fill the fields with your own text → Download → open in Word
and confirm your text sits inside the original styling untouched; repeat with a `.pptx`; try "Draft
with AI" from a brief; delete a template; confirm demo is read-only. Per-PR gate: server ruff + mypy
+ pytest; client tsc + eslint + prettier + build + vitest; then `/code-review` + `/security-review`,
owner commit/push approval, PR into `dev`.
