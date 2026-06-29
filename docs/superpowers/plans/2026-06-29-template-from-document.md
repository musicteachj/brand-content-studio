# Fill a Branded Template from an Uploaded Document — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user upload an unbranded `.docx`/`.pptx`/`.pdf`/`.txt`/`.md`, extract its content, and have an AI map that content onto a branded template's `{{placeholders}}` — producing a branded, on-layout document.

**Architecture:** "AI-fill, but sourced from an uploaded document instead of a brief." Reuses the entire Phase 5 fill→review→render pipeline. New: a `content_extraction` service (Office/PDF/text → bounded plain text), a content-sourced fill prompt, one route returning the existing `{values}` shape, and one upload control on the fill UI. Ephemeral, demo-allowed, no new storage.

**Tech Stack:** FastAPI + python-docx/python-pptx/pdfplumber (all already installed) + pytest (server); React + react-query + Vitest (client). Server cmds from `server/` (`.venv/bin/...`, model-touching runs prefixed `env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY`); client cmds from `client/` via `./node_modules/.bin/<tool>`.

**Spec:** `docs/superpowers/specs/2026-06-29-template-from-document-design.md`

**Branch:** `feat/template-from-document` (off `dev`, already created; spec committed).

**File structure:**
- Create `server/app/services/content_extraction.py` — extract bounded plain text from a source file (one responsibility).
- Create `server/tests/test_content_extraction.py`.
- Modify `server/app/prompts/template_fill.py` — add `build_fill_user_from_content`.
- Modify `server/app/routes/templates.py` — add the `fill-from-document` route.
- Modify `server/tests/test_templates.py` — route tests (reuse the harness).
- Modify `client/src/api/templates.ts` — add `fillTemplateFromDocument` + test `client/src/api/templates.test.ts`.
- Modify `client/src/features/templates/TemplatesPage.tsx` — the "Fill from a document" control.
- Docs: `docs/DECISIONS.md`, `CHANGELOG.md`.

---

### Task 1: Content extraction service

**Files:**
- Create: `server/app/services/content_extraction.py`
- Test: `server/tests/test_content_extraction.py`

- [ ] **Step 1: Write the failing tests**

Create `server/tests/test_content_extraction.py`:

```python
"""Extract bounded plain text from an uploaded source document (docx/pptx/pdf/
text). Office fixtures are built in-memory; no model calls."""
import io

import pytest
from docx import Document
from pptx import Presentation
from pptx.util import Inches

from app.services.content_extraction import (
    MAX_SOURCE_CHARS,
    UnsupportedSourceError,
    extract_document_text,
)


def _docx(*, paras=(), heading=None) -> bytes:
    doc = Document()
    if heading:
        doc.add_heading(heading, level=1)
    for p in paras:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _pptx(*lines: str) -> bytes:
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    tf = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(2)).text_frame
    for i, line in enumerate(lines):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.add_run().text = line
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def test_extract_docx_keeps_heading_and_body():
    out = extract_document_text(_docx(heading="The Plan", paras=["First point.", "Second point."]), "plan.docx")
    assert "# The Plan" in out
    assert "First point." in out and "Second point." in out


def test_extract_pptx_prefixes_slides():
    out = extract_document_text(_pptx("Title slide", "a bullet"), "deck.pptx")
    assert "Slide 1:" in out
    assert "Title slide" in out and "a bullet" in out


def test_extract_text_and_markdown():
    assert "hello world" in extract_document_text(b"hello world", "notes.txt")
    assert "# Heading" in extract_document_text(b"# Heading\n\nbody", "notes.md")


def test_extract_truncates_to_budget():
    big = ("word " * 20000).encode("utf-8")  # ~100k chars
    out = extract_document_text(big, "big.txt")
    assert len(out) == MAX_SOURCE_CHARS


def test_extract_rejects_unsupported_type():
    with pytest.raises(UnsupportedSourceError):
        extract_document_text(b"\x00\x01", "image.png")


def test_extract_empty_raises_valueerror():
    with pytest.raises(ValueError):
        extract_document_text(_docx(paras=["   "]), "blank.docx")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_content_extraction.py -q`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Create `server/app/services/content_extraction.py`**

```python
"""Extract a bounded, lightly-structured plain-text representation of an uploaded
source document, for mapping onto a branded template's placeholders. Distinct
from `rag/loaders` (which yields Sections for chunking) — here we want one
readable blob for the fill prompt. Pure + synchronous so it's unit-testable; the
route runs it off the event loop under a timeout."""
from __future__ import annotations

import io
import os

MAX_SOURCE_CHARS = 40000  # ~10-12 pages / ~10k input tokens — generous, bounded
_MAX_PDF_PAGES = 80

_TEXT_EXTS = {".txt", ".md", ".markdown"}


class UnsupportedSourceError(ValueError):
    """The uploaded source file type can't be extracted."""


def extract_document_text(data: bytes, filename: str) -> str:
    """Return up to MAX_SOURCE_CHARS of plain text from a docx/pptx/pdf/txt/md
    source. Raises UnsupportedSourceError for other types, ValueError if no text
    could be extracted."""
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".docx":
        text = _extract_docx(data)
    elif ext == ".pptx":
        text = _extract_pptx(data)
    elif ext == ".pdf":
        text = _extract_pdf(data)
    elif ext in _TEXT_EXTS:
        text = data.decode("utf-8", errors="replace")
    else:
        raise UnsupportedSourceError(f"Unsupported source type: {ext or '(none)'}")
    text = text.strip()
    if not text:
        raise ValueError("No extractable text found in the document.")
    return text[:MAX_SOURCE_CHARS]


def _extract_docx(data: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    lines: list[str] = []
    for p in doc.paragraphs:
        t = p.text.strip()
        if not t:
            continue
        style = (p.style.name or "").lower() if p.style else ""
        if "heading" in style:
            lines.append(f"# {t}")
        elif "list" in style:
            lines.append(f"- {t}")
        else:
            lines.append(t)
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def _extract_pptx(data: bytes) -> str:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    out: list[str] = []
    for i, slide in enumerate(prs.slides, start=1):
        parts: list[str] = []
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                parts.append(shape.text_frame.text.strip())
            elif shape.has_table:
                for row in shape.table.rows:
                    cells = [c.text.strip() for c in row.cells if c.text.strip()]
                    if cells:
                        parts.append(" | ".join(cells))
        if parts:
            out.append(f"Slide {i}:\n" + "\n".join(parts))
    return "\n\n".join(out)


def _extract_pdf(data: bytes) -> str:
    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages[:_MAX_PDF_PAGES]:
            t = page.extract_text() or ""
            if t.strip():
                pages.append(t)
    return "\n\n".join(pages)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_content_extraction.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add server/app/services/content_extraction.py server/tests/test_content_extraction.py
git commit -m "feat(template-from-doc): content extraction (docx/pptx/pdf/text → bounded text)"
```

---

### Task 2: Content-sourced fill prompt

**Files:**
- Modify: `server/app/prompts/template_fill.py`
- Test: `server/tests/test_templates.py`

- [ ] **Step 1: Add the failing test** — in `server/tests/test_templates.py`, extend the import from `template_fill` and add a test next to `test_fill_prompt_builders_nonempty`:

Change the import line:

```python
from app.prompts.template_fill import (
    build_fill_system,
    build_fill_tool,
    build_fill_user,
    build_fill_user_from_content,
)
```

Add the test:

```python
def test_build_fill_user_from_content_includes_content_and_fields():
    out = build_fill_user_from_content("The Q3 plan: grow EU sales.", ["title", "summary"])
    assert "The Q3 plan: grow EU sales." in out
    assert "title" in out and "summary" in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_templates.py::test_build_fill_user_from_content_includes_content_and_fields -q`
Expected: FAIL — `build_fill_user_from_content` doesn't exist.

- [ ] **Step 3: Add `build_fill_user_from_content`** to `server/app/prompts/template_fill.py` (after `build_fill_user`):

```python
def build_fill_user_from_content(content: str, placeholders: list[str]) -> str:
    return "\n".join(
        [
            "Source document content to map into the template's fields:",
            '"""',
            content.strip(),
            '"""',
            "",
            "Map the source content onto these fields (call the fill_template tool with a "
            "value for each). Condense to fit each field; leave a field empty if the source "
            "has nothing for it:",
            ", ".join(placeholders),
        ]
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_templates.py::test_build_fill_user_from_content_includes_content_and_fields -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/app/prompts/template_fill.py server/tests/test_templates.py
git commit -m "feat(template-from-doc): content-sourced fill prompt"
```

---

### Task 3: `fill-from-document` route

**Files:**
- Modify: `server/app/routes/templates.py`
- Test: `server/tests/test_templates.py`

- [ ] **Step 1: Add the failing tests** — in `server/tests/test_templates.py`, after `test_ai_fill_returns_values`, add:

```python
@pytest.mark.asyncio
async def test_fill_from_document_maps_content(tpl_client):
    t = await _upload(tpl_client)
    src = _docx_bytes("Welcome to Acme", "We supply hempcrete.")
    resp = await tpl_client.post(
        f"{_base()}/{t['id']}/fill-from-document",
        files={"file": ("draft.docx", src, DOCX_CT)},
    )
    assert resp.status_code == 200
    assert resp.json()["values"] == {"client_name": "draft client_name"}


@pytest.mark.asyncio
async def test_fill_from_document_rejects_bad_type(tpl_client):
    t = await _upload(tpl_client)
    resp = await tpl_client.post(
        f"{_base()}/{t['id']}/fill-from-document",
        files={"file": ("logo.png", b"\x89PNG", "image/png")},
    )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_fill_from_document_missing_template_404(tpl_client):
    resp = await tpl_client.post(
        f"{_base()}/{ObjectId()}/fill-from-document",
        files={"file": ("draft.docx", _docx_bytes("hi"), DOCX_CT)},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_fill_from_document_allowed_for_demo(test_db, tmp_path, monkeypatch):
    owner = await _mk(test_db, tmp_path, monkeypatch)
    async with owner:
        t = await _upload(owner)
    app.dependency_overrides.clear()
    get_storage.cache_clear()
    demo = await _mk(test_db, tmp_path, monkeypatch, is_demo=True)
    async with demo:
        resp = await demo.post(
            f"{_base()}/{t['id']}/fill-from-document",
            files={"file": ("draft.docx", _docx_bytes("hi"), DOCX_CT)},
        )
    app.dependency_overrides.clear()
    get_storage.cache_clear()
    assert resp.status_code == 200
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_templates.py -k fill_from_document -q`
Expected: FAIL — route returns 404/405 (not defined).

- [ ] **Step 3: Add the route** to `server/app/routes/templates.py`.

(a) Add imports at the top (with the others):

```python
import asyncio
```
```python
from app.services.content_extraction import extract_document_text
```

(b) Add constants near `MAX_TEMPLATE_BYTES`:

```python
MAX_SOURCE_BYTES = 10 * 1024 * 1024  # 10 MB
SOURCE_PARSE_TIMEOUT_S = 30
_SOURCE_EXTS = {".docx", ".pptx", ".pdf", ".txt", ".md", ".markdown"}
```

(c) Add the route (after `ai_fill_template`, before `render_template`):

```python
@router.post("/{template_id}/fill-from-document", response_model=TemplateAiFillResponse)
async def fill_template_from_document(
    template_id: str,
    file: UploadFile,
    workspace: dict = Depends(get_workspace_or_404),
    service: GenerationService = Depends(GenerationService),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Draft each placeholder by mapping an uploaded document's content onto the
    template's fields. Generative + nothing persisted → allowed for the demo
    user; the source file is parsed in-memory and discarded."""
    doc = await template_service.get_template(db, workspace["_id"], template_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    filename = file.filename or "source"
    if os.path.splitext(filename)[1].lower() not in _SOURCE_EXTS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported document. Upload a .docx, .pptx, .pdf, .txt, or .md file.",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file.")
    if len(data) > MAX_SOURCE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Document exceeds the {MAX_SOURCE_BYTES // (1024 * 1024)} MB limit.",
        )
    placeholders = doc.get("placeholders") or []
    if not placeholders:
        return TemplateAiFillResponse(values={})
    try:
        content = await asyncio.wait_for(
            asyncio.to_thread(extract_document_text, data, filename), SOURCE_PARSE_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Parsing the document timed out — try a smaller or simpler file.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    tool = template_fill.build_fill_tool(placeholders)
    result = await service.fill_template_values(
        template_fill.build_fill_system(),
        template_fill.build_fill_user_from_content(content, placeholders),
        tool,
    )
    return TemplateAiFillResponse(values=template_service.clamp_values(result, placeholders))
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_templates.py -k fill_from_document -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add server/app/routes/templates.py server/tests/test_templates.py
git commit -m "feat(template-from-doc): demo-allowed fill-from-document route"
```

---

### Task 4: Server gate

- [ ] **Step 1: ruff + mypy + full pytest**

Run: `cd server && .venv/bin/ruff check app tests && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/mypy app && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest -q`
Expected: ruff clean; mypy clean; all pass (≈124).

- [ ] **Step 2: Fix anything; commit if changed**

```bash
git add -A && git commit -m "chore(template-from-doc): server gate green"
```

---

### Task 5: Client API function

**Files:**
- Modify: `client/src/api/templates.ts`
- Test: `client/src/api/templates.test.ts`

- [ ] **Step 1: Write the failing test**

Create `client/src/api/templates.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { fillTemplateFromDocument } from "./templates";

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: { post } }));

afterEach(() => vi.clearAllMocks());

describe("fillTemplateFromDocument", () => {
  it("posts the file as multipart and returns the values map", async () => {
    post.mockResolvedValue({ data: { values: { title: "Mapped" } } });
    const file = new File(["hi"], "draft.docx");
    const values = await fillTemplateFromDocument("ws1", "t1", file);
    expect(values).toEqual({ title: "Mapped" });
    const [url, body] = post.mock.calls[0];
    expect(url).toBe("/workspaces/ws1/templates/t1/fill-from-document");
    expect(body).toBeInstanceOf(FormData);
    expect((body as FormData).get("file")).toBe(file);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd client && ./node_modules/.bin/vitest run src/api/templates.test.ts`
Expected: FAIL — `fillTemplateFromDocument` not exported.

- [ ] **Step 3: Add `fillTemplateFromDocument`** to `client/src/api/templates.ts` (after `useAiFillTemplate`, mirroring the plain `renderTemplate` function):

```ts
/** Map an uploaded source document's content onto a template's placeholders. */
export async function fillTemplateFromDocument(
  workspaceId: string,
  templateId: string,
  file: File,
): Promise<Record<string, string>> {
  const form = new FormData();
  form.append("file", file);
  const resp = await api.post<{ values: Record<string, string> }>(
    `/workspaces/${workspaceId}/templates/${templateId}/fill-from-document`,
    form,
  );
  return resp.data.values;
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd client && ./node_modules/.bin/vitest run src/api/templates.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add client/src/api/templates.ts client/src/api/templates.test.ts
git commit -m "feat(template-from-doc): client fillTemplateFromDocument"
```

---

### Task 6: Fill UI — "Fill from a document" control + client gate

**Files:**
- Modify: `client/src/features/templates/TemplatesPage.tsx`

- [ ] **Step 1: Import the function + an icon.** In `client/src/features/templates/TemplatesPage.tsx`, extend the `@/api/templates` import to include `fillTemplateFromDocument`, and ensure `FileUp` is imported from `lucide-react` (add it to the existing lucide import).

```ts
import { fillTemplateFromDocument, renderTemplate, useAiFillTemplate, /* …existing… */ } from "@/api/templates";
```

- [ ] **Step 2: Add state + handler in `FillPanel`.** After the existing `const [error, setError] = useState<string | null>(null);` in `FillPanel`, add:

```tsx
  const docRef = useRef<HTMLInputElement>(null);
  const [fillingFromDoc, setFillingFromDoc] = useState(false);

  async function fillFromDocument(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !workspaceId) return;
    setFillingFromDoc(true);
    setError(null);
    try {
      const filled = await fillTemplateFromDocument(workspaceId, template.id, file);
      setValues(mergeFilled(template.placeholders, filled));
    } catch {
      setError("Couldn’t read that document. Use a .docx, .pptx, .pdf, .txt, or .md under 10 MB.");
    } finally {
      setFillingFromDoc(false);
    }
  }
```

(`useRef` is already imported at the top of the file.)

- [ ] **Step 3: Add the control** inside the dashed "Draft with AI" box, after the `<div>` wrapping the "Draft with AI" button (still inside the `border-dashed` container):

```tsx
            <div className="flex items-center gap-2 border-t border-border pt-2.5">
              <input
                ref={docRef}
                type="file"
                accept=".docx,.pptx,.pdf,.txt,.md,.markdown"
                className="hidden"
                onChange={fillFromDocument}
              />
              <Button
                size="sm"
                variant="ghost"
                onClick={() => docRef.current?.click()}
                loading={fillingFromDoc}
              >
                <FileUp className="h-4 w-4" aria-hidden />
                Fill from a document
              </Button>
              <span className="text-[11px] text-muted-foreground">
                Content is mapped and condensed to fit the template.
              </span>
            </div>
```

- [ ] **Step 4: Typecheck + lint + format + test + build (client gate)**

Run: `cd client && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/eslint src && ./node_modules/.bin/prettier --write "src/**/*.{ts,tsx}" && ./node_modules/.bin/vitest run && ./node_modules/.bin/vite build`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add client/src/features/templates/TemplatesPage.tsx
git commit -m "feat(template-from-doc): 'Fill from a document' control on the template fill UI"
```

---

### Task 7: Docs

**Files:** `docs/DECISIONS.md`, `CHANGELOG.md`

- [ ] **Step 1: DECISIONS** — add a row after the `#29` row:

```
| 30 | Template fill from an uploaded document | Users can upload an unbranded `.docx`/`.pptx`/`.pdf`/`.txt`/`.md` and have its content mapped onto a branded template's `{{placeholders}}` — "bring a rough draft, get the official branded version." Implemented as **AI-fill sourced from a document instead of a brief**: a new `content_extraction` service (python-docx/python-pptx/pdfplumber → a bounded ≤40k-char blob, off-loop + timeout) feeds a content-sourced fill prompt through the existing `build_fill_tool`/`fill_template_values`/`clamp_values` path; the new `POST …/templates/{id}/fill-from-document` returns the same `{values}` shape as `ai-fill`, so the review-and-render finish is unchanged. **Fidelity = fixed-slots-condense** (content is mapped/summarized into whatever placeholders the template has; the template layout is authoritative per #24), made safe by the existing review-before-render step. Generative + nothing persisted → **demo-allowed**; source parsed in-memory and discarded (no new storage/collection). **Deferred:** author-written placeholder *hints* (the top quality follow-up) and structure-preserving output via docx repeatable regions. | every branded path started from a brief or typed values — no way to restyle an existing unbranded doc into the brand template | Near-total reuse of the Phase 5 fill pipeline; the only new work is extraction + one prompt + one route + one control. Fixed-slots fidelity keeps docx/pptx parity (loop regions are infeasible in pptx) and matches the "template styling is authoritative" decision. |
```

- [ ] **Step 2: CHANGELOG** — under `## [Unreleased]`, add at the top:

```markdown
### Added — Fill a branded template from an uploaded document

Upload an unbranded `.docx`/`.pptx`/`.pdf`/`.txt`/`.md` onto one of your branded templates and the content is extracted and mapped onto the template's `{{placeholders}}` — a rough draft in, the official branded version out. It's AI-fill sourced from a document instead of a brief: a new content-extraction step (≤40k chars, off-loop + timeout) feeds the existing template fill tool, and the new `POST …/templates/{id}/fill-from-document` returns the same `{values}` shape, so you still review/edit before rendering. Content is mapped and condensed to fit the template's fixed slots. Generative + nothing persisted → demo-allowed; the source is parsed in-memory and discarded. See [`docs/DECISIONS.md`](./docs/DECISIONS.md) (#30). Placeholder hints + structure-preserving output are noted as fast-follows. Tests: pytest (+11) — extraction (docx/pptx/text/truncate/unsupported/empty) + the route; vitest (+1) — the client request.
```

- [ ] **Step 3: Commit**

```bash
git add docs/DECISIONS.md CHANGELOG.md
git commit -m "docs(template-from-doc): DECISIONS #30 + CHANGELOG"
```

---

### Task 8: Review, verify, PR

- [ ] **Step 1: Re-run both gates** (Task 4 + Task 6 Step 4) — confirm green.
- [ ] **Step 2: `/code-review`** the branch diff; fix real findings.
- [ ] **Step 3: `/security-review`**; fix real findings. (Surface: untrusted Office/PDF parsing is bounded (size + page + char caps, off-loop timeout); no zip-bomb amplification beyond the 10 MB cap is persisted; extraction is read-only and discarded; route is ownership-scoped + demo-allowed-by-design since nothing is written.)
- [ ] **Step 4: Live verify (owner):** Templates → upload a branded `.docx` template with a few `{{placeholders}}` → open Fill → **Fill from a document** → upload a plain/unbranded draft → the placeholder fields populate with mapped content → edit if needed → Download → the file is the branded template with the draft's content. Try a `.pptx` source and a `.pdf` source.
- [ ] **Step 5: Owner commit/push approval**, then push `feat/template-from-document` and open a PR into `dev` (REST API + keychain token; no `gh`).

---

## Self-Review

**Spec coverage:** content extraction docx/pptx/pdf/txt/md + off-loop/timeout/truncate/empty (Task 1 + Task 3 route wrapper) ✓; content-sourced prompt reusing the fill tool (Task 2) ✓; route returning the `ai-fill` `{values}` shape, demo-allowed, ephemeral (Task 3) ✓; scope guards — 10 MB / extension allowlist / 40k chars / existing clamps (Task 1 + Task 3) ✓; client upload control feeding the same review fields (Tasks 5–6) ✓; tests server + client (throughout) ✓; docs (Task 7) ✓. Fast-follows (hints, structure-preserving) explicitly deferred ✓.

**Placeholder scan:** none — every code step is concrete.

**Type consistency:** `extract_document_text(data, filename)` + `MAX_SOURCE_CHARS` + `UnsupportedSourceError` (Task 1) match their uses in the route (Task 3) and tests. `build_fill_user_from_content(content, placeholders)` (Task 2) matches the route call (Task 3). The route path `/{template_id}/fill-from-document` matches the client `fillTemplateFromDocument` URL (Task 5) and the server tests (Task 3). `fillTemplateFromDocument(workspaceId, templateId, file) -> Record<string,string>` (Task 5) matches its `FillPanel` use via `mergeFilled` (Task 6), which already exists and is the same merge used by the brief path.
```
