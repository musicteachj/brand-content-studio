# On-Brand Document Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an owner upload branded `.docx`/`.pptx` templates with `{{placeholders}}` and pour content into them — their own text (primary) or an AI draft (optional) — producing a download that keeps the template's exact styling.

**Architecture:** A standalone Templates subsystem, independent of the RAG/generate pipeline. Upload → discover `{{placeholders}}` → store file + metadata in a new `templates` collection. Fill values (manual form or one AI tool-use call) → render by swapping **only** text (`docxtpl` for docx, paragraph-level replace for pptx) → return the file for download. The template's styling is authoritative — no `brand_profile` injection. Renders are ephemeral (not persisted).

**Tech Stack:** FastAPI + Motor + Pydantic v2 + docxtpl/python-pptx/AsyncAnthropic (server); React + Vite + TS + react-query (client). Tests: pytest + vitest.

**Spec:** `docs/superpowers/specs/2026-06-26-on-brand-templates-design.md`

**Working dir for server commands:** `server/`. Run via the venv (`.venv/bin/...`), prefix model-touching/import runs with `env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY`. Branch: `feat/5-templates` (already created off `dev`).

**File structure (created/modified):**
- `server/app/services/storage_service.py` — `build_template_key`.
- `server/app/services/template_service.py` (new) — placeholder discovery, fill/render, Mongo CRUD.
- `server/app/prompts/template_fill.py` (new) — dynamic strict fill tool + prompts.
- `server/app/services/generation_service.py` — `fill_template_values` method.
- `server/app/models/template.py` (new) — response + request models.
- `server/app/routes/templates.py` (new) — upload / list / delete / ai-fill / render.
- `server/app/main.py` — mount the router; `server/app/database.py` — index; `server/app/services/workspace_service.py` — drop templates on workspace delete.
- `server/requirements.txt` — add `docxtpl`.
- `server/tests/test_templates.py` (new).
- `client/src/types/index.ts`, `client/src/api/templates.ts` (new).
- `client/src/features/templates/TemplatesPage.tsx` (new) + `templates.ts` helpers (+ test).
- `client/src/components/layout/SideNav.tsx`, `client/src/App.tsx`.
- Docs: `docs/DECISIONS.md`, `docs/PLAN.md`, `CHANGELOG.md`, `docs/DESIGN.md`.

---

### Task 1: `build_template_key` + `docxtpl` dependency

**Files:**
- Modify: `server/app/services/storage_service.py`
- Modify: `server/requirements.txt`
- Test: `server/tests/test_templates.py`

- [ ] **Step 1: Write the failing test**

Create `server/tests/test_templates.py`:

```python
"""On-brand document templates (Phase 5). Discovery + fill are pure (fixtures
built in-memory with python-docx/python-pptx); routes are tested with the AI
fill faked (no model call)."""
from app.services.storage_service import build_template_key


def test_build_template_key_is_server_derived():
    key = build_template_key("ws1", "t1", "Quarterly Report.docx")
    assert key == "ws1/templates/t1/Quarterly_Report.docx"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && .venv/bin/python -m pytest tests/test_templates.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_template_key'`.

- [ ] **Step 3: Add `build_template_key`** to `server/app/services/storage_service.py` (after `build_document_key`):

```python
def build_template_key(workspace_id: str, template_id: str, filename: str) -> str:
    """Uploaded fill-in templates live under a `templates/` prefix, separate from
    the ingested corpus, card images, and generated documents."""
    return f"{safe_filename(workspace_id)}/templates/{safe_filename(template_id)}/{safe_filename(filename)}"
```

- [ ] **Step 4: Add the dependency** — in `server/requirements.txt`, under the Documents section:

```
docxtpl>=0.16  # Jinja2-for-Word template fill (Phase 5); depends on python-docx
```

Install it: `cd server && .venv/bin/pip install "docxtpl>=0.16"`
Expected: installs docxtpl + jinja2.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd server && .venv/bin/python -m pytest tests/test_templates.py -q`
Expected: PASS (1 passed).

- [ ] **Step 6: Commit**

```bash
git add server/app/services/storage_service.py server/requirements.txt server/tests/test_templates.py
git commit -m "feat(templates): build_template_key + docxtpl dependency"
```

---

### Task 2: Placeholder discovery (docx + pptx)

**Files:**
- Create: `server/app/services/template_service.py`
- Test: `server/tests/test_templates.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_templates.py`)

```python
import io

from docx import Document
from pptx import Presentation
from pptx.util import Inches

from app.services.template_service import discover_placeholders


def _docx_bytes(*paragraphs: str) -> bytes:
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _pptx_bytes(*lines: str) -> bytes:
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(2))
    tf = box.text_frame
    for i, line in enumerate(lines):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.add_run().text = line
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def test_discover_placeholders_docx():
    data = _docx_bytes("Hello {{client_name}}", "Re: {{topic}} and {{topic}}")
    found = discover_placeholders(data, "docx")
    assert set(found) == {"client_name", "topic"}  # de-duped


def test_discover_placeholders_pptx_in_order():
    data = _pptx_bytes("{{title}}", "by {{author}}")
    assert discover_placeholders(data, "pptx") == ["title", "author"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && .venv/bin/python -m pytest tests/test_templates.py -q`
Expected: FAIL — `ModuleNotFoundError: app.services.template_service`.

- [ ] **Step 3: Create `server/app/services/template_service.py`**

```python
"""On-brand document templates (Phase 5). Discover the `{{placeholder}}` tags in
an uploaded .docx/.pptx, fill them with values (the user's own text or an AI
draft), and render — swapping ONLY text, never the template's styling. docx via
docxtpl (Jinja2-for-Word); pptx via paragraph-level run replacement (PowerPoint
splits a tag across runs, so we substitute on the joined paragraph text)."""
from __future__ import annotations

import re
from io import BytesIO

from docxtpl import DocxTemplate
from pptx import Presentation

MAX_PLACEHOLDERS = 40
MAX_VALUE_LEN = 2000
_TAG = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def discover_placeholders(data: bytes, fmt: str) -> list[str]:
    """The `{{tags}}` declared in the template. docx: docxtpl's Jinja analysis
    (robust to run-splitting), sorted for determinism. pptx: scan joined
    paragraph text, de-duped in first-seen order."""
    if fmt == "docx":
        names = DocxTemplate(BytesIO(data)).get_undeclared_template_variables()
        return sorted(names)
    seen: list[str] = []
    prs = Presentation(BytesIO(data))
    for slide in prs.slides:
        for frame in _text_frames(slide.shapes):
            for para in frame.paragraphs:
                joined = "".join(r.text for r in para.runs)
                for name in _TAG.findall(joined):
                    if name not in seen:
                        seen.append(name)
    return seen


def _text_frames(shapes):  # type: ignore[no-untyped-def]
    """Yield every text frame in a shape tree — text boxes/placeholders + table cells."""
    for shape in shapes:
        if shape.has_text_frame:
            yield shape.text_frame
        if shape.has_table:
            for row in shape.table.rows:
                for cell in row.cells:
                    yield cell.text_frame
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && .venv/bin/python -m pytest tests/test_templates.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add server/app/services/template_service.py server/tests/test_templates.py
git commit -m "feat(templates): discover_placeholders (docx + pptx)"
```

---

### Task 3: Fill + render + clamp (styles preserved)

**Files:**
- Modify: `server/app/services/template_service.py`
- Test: `server/tests/test_templates.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_templates.py`)

```python
from docx import Document
from docx.shared import Pt, RGBColor

from app.services.template_service import clamp_values, render


def _styled_docx() -> bytes:
    doc = Document()
    run = doc.add_paragraph().add_run("{{headline}}")
    run.font.size = Pt(22)
    run.font.color.rgb = RGBColor(0x1C, 0x3A, 0x2E)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_render_docx_swaps_text_preserves_style():
    out = render(_styled_docx(), {"headline": "Carbon in the wall"}, "docx")
    doc = Document(io.BytesIO(out))
    run = doc.paragraphs[0].runs[0]
    assert run.text == "Carbon in the wall"
    assert run.font.size == Pt(22)  # styling untouched
    assert run.font.color.rgb == RGBColor(0x1C, 0x3A, 0x2E)


def test_render_pptx_swaps_fragmented_tag_preserves_style():
    # A tag split across runs (as PowerPoint often stores it).
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    para = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(2)).text_frame.paragraphs[0]
    for frag in ("{{", "title", "}}"):
        r = para.add_run()
        r.text = frag
        r.font.size = Pt(40)
    buf = io.BytesIO()
    prs.save(buf)

    out = render(buf.getvalue(), {"title": "Verdure"}, "pptx")
    p2 = Presentation(io.BytesIO(out)).slides[0].shapes[0].text_frame.paragraphs[0]
    assert "".join(r.text for r in p2.runs) == "Verdure"
    assert p2.runs[0].font.size == Pt(40)  # first run's style preserved


def test_clamp_values_drops_unknown_and_clamps_length():
    out = clamp_values({"a": "x" * 5000, "z": "nope"}, ["a"])
    assert set(out) == {"a"}
    assert len(out["a"]) == 2000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && .venv/bin/python -m pytest tests/test_templates.py -q`
Expected: FAIL — `cannot import name 'render'`.

- [ ] **Step 3: Add fill/render/clamp** to `server/app/services/template_service.py`:

```python
def clamp_values(values: dict[str, str], placeholders: list[str]) -> dict[str, str]:
    """Keep only known placeholders; clamp each value's length. Missing keys are
    left out (they render blank)."""
    allowed = set(placeholders)
    return {
        k: str(v if v is not None else "")[:MAX_VALUE_LEN]
        for k, v in (values or {}).items()
        if k in allowed
    }


def render(data: bytes, values: dict[str, str], fmt: str) -> bytes:
    return _fill_docx(data, values) if fmt == "docx" else _fill_pptx(data, values)


def _fill_docx(data: bytes, values: dict[str, str]) -> bytes:
    tpl = DocxTemplate(BytesIO(data))
    tpl.render(values)  # Jinja: an undefined/missing var renders as empty string
    out = BytesIO()
    tpl.save(out)
    return out.getvalue()


def _fill_pptx(data: bytes, values: dict[str, str]) -> bytes:
    prs = Presentation(BytesIO(data))
    for slide in prs.slides:
        for frame in _text_frames(slide.shapes):
            for para in frame.paragraphs:
                _fill_paragraph(para, values)
    out = BytesIO()
    prs.save(out)
    return out.getvalue()


def _fill_paragraph(para, values: dict[str, str]) -> None:  # type: ignore[no-untyped-def]
    """Substitute on the joined paragraph text (a tag can span runs), then write
    the result into the first run (keeping its formatting) and clear the rest."""
    runs = para.runs
    if not runs:
        return
    joined = "".join(r.text for r in runs)
    if "{{" not in joined:
        return
    replaced = _TAG.sub(lambda m: str(values.get(m.group(1), "")), joined)
    if replaced == joined:
        return
    runs[0].text = replaced
    for r in runs[1:]:
        r.text = ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && .venv/bin/python -m pytest tests/test_templates.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add server/app/services/template_service.py server/tests/test_templates.py
git commit -m "feat(templates): fill/render docx+pptx (styles preserved) + clamp"
```

---

### Task 4: Template models

**Files:**
- Create: `server/app/models/template.py`
- Test: `server/tests/test_templates.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_templates.py`)

```python
from app.models.template import TemplateAiFillRequest, TemplateRenderRequest, TemplateResponse


def test_template_models_shape():
    t = TemplateResponse(id="t1", workspace_id="w1", name="Report", format="docx",
                         storage_key="k", placeholders=["title"])
    assert t.format == "docx" and t.placeholders == ["title"]
    assert TemplateRenderRequest(values={"title": "x"}).values == {"title": "x"}
    assert TemplateAiFillRequest(brief="a deck about hempcrete").brief
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && .venv/bin/python -m pytest tests/test_templates.py -q`
Expected: FAIL — `ModuleNotFoundError: app.models.template`.

- [ ] **Step 3: Create `server/app/models/template.py`**

```python
"""Template models (Phase 5). Mirror server/app/models/* — no `_id`; routes
serialize ObjectId → str `id` on the way out."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

TemplateFormat = Literal["docx", "pptx"]


class TemplateResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    format: TemplateFormat
    storage_key: str
    placeholders: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class TemplateRenderRequest(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


class TemplateAiFillRequest(BaseModel):
    brief: str = Field(min_length=1, max_length=2000)


class TemplateAiFillResponse(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && .venv/bin/python -m pytest tests/test_templates.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add server/app/models/template.py server/tests/test_templates.py
git commit -m "feat(templates): template models"
```

---

### Task 5: Template Mongo CRUD

**Files:**
- Modify: `server/app/services/template_service.py`
- (Covered by route tests in Task 7.)

- [ ] **Step 1: Add CRUD** to `server/app/services/template_service.py`

Add imports at the top (below the existing imports):

```python
from typing import Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.common import serialize_doc, utcnow
from app.models.template import TemplateResponse
```

Add the functions at the end of the file:

```python
def _to_response(doc: dict) -> TemplateResponse:
    return TemplateResponse(**serialize_doc(doc))


async def create_template(
    db: AsyncIOMotorDatabase,
    workspace_oid: ObjectId,
    owner_oid: ObjectId,
    *,
    template_oid: ObjectId,
    name: str,
    fmt: str,
    storage_key: str,
    placeholders: list[str],
) -> TemplateResponse:
    doc = {
        "_id": template_oid,
        "workspace_id": workspace_oid,
        "owner_id": owner_oid,
        "name": name,
        "format": fmt,
        "storage_key": storage_key,
        "placeholders": placeholders,
        "created_at": utcnow(),
    }
    await db.templates.insert_one(doc)
    return _to_response(doc)


async def list_templates(db: AsyncIOMotorDatabase, workspace_oid: ObjectId) -> list[TemplateResponse]:
    cursor = db.templates.find({"workspace_id": workspace_oid}).sort("created_at", -1)
    return [_to_response(doc) async for doc in cursor]


async def get_template(
    db: AsyncIOMotorDatabase, workspace_oid: ObjectId, template_id: str
) -> Optional[dict]:
    try:
        oid = ObjectId(template_id)
    except Exception:
        return None
    return await db.templates.find_one({"_id": oid, "workspace_id": workspace_oid})


async def delete_template(db: AsyncIOMotorDatabase, doc: dict) -> None:
    await db.templates.delete_one({"_id": doc["_id"]})
```

- [ ] **Step 2: Verify imports/lint**

Run: `cd server && .venv/bin/ruff check app/services/template_service.py && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/mypy app/services/template_service.py`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add server/app/services/template_service.py
git commit -m "feat(templates): Mongo CRUD for templates"
```

---

### Task 6: AI-fill prompt (dynamic tool) + service method

**Files:**
- Create: `server/app/prompts/template_fill.py`
- Modify: `server/app/services/generation_service.py`
- Test: `server/tests/test_templates.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_templates.py`)

```python
from app.prompts.template_fill import build_fill_system, build_fill_tool, build_fill_user


def test_build_fill_tool_uses_placeholder_names():
    tool = build_fill_tool(["title", "body"])
    props = tool["input_schema"]["properties"]
    assert set(props) == {"title", "body"}
    assert tool["input_schema"]["required"] == ["title", "body"]
    assert tool["strict"] is True


def test_fill_prompt_builders_nonempty():
    assert build_fill_system().strip()
    assert "title" in build_fill_user("a brief", ["title"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && .venv/bin/python -m pytest tests/test_templates.py -q`
Expected: FAIL — `ModuleNotFoundError: app.prompts.template_fill`.

- [ ] **Step 3: Create `server/app/prompts/template_fill.py`**

```python
"""AI-draft fill for templates (Phase 5, optional path). A forced strict tool-use
call whose schema is built from THIS template's placeholder names, so the model
returns exactly one value per placeholder. Tone is secondary here — the value of
templates is consistent styling, not bespoke prose — so the prompt stays concise."""
from __future__ import annotations

from typing import Any

_FILL_SYSTEM = """You fill in the fields of a branded document template. You are given the template's field names and a short brief. Return concise, professional copy for each field by calling the provided tool. Keep each value short and appropriate to its field name; do not invent specific statistics or facts that aren't in the brief. Plain text only — no markdown."""


def build_fill_system() -> str:
    return _FILL_SYSTEM


def build_fill_user(brief: str, placeholders: list[str]) -> str:
    return "\n".join(
        [
            f'Brief: "{brief.strip()}"',
            "",
            "Fields to fill (call the fill_template tool with a value for each):",
            ", ".join(placeholders),
        ]
    )


def build_fill_tool(placeholders: list[str]) -> dict[str, Any]:
    """A strict tool whose properties are exactly this template's placeholders."""
    props = {name: {"type": "string", "description": f"Copy for the '{name}' field."} for name in placeholders}
    return {
        "name": "fill_template",
        "description": "Provide a value for each field of the document template.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": props,
            "required": list(placeholders),
        },
    }
```

- [ ] **Step 4: Add the service method** to `server/app/services/generation_service.py`

Add a constant near the other `MAX_TOKENS` constants:

```python
TEMPLATE_FILL_MAX_TOKENS = 1500
```

Add a method on `GenerationService` (after `extract_document_sections`):

```python
    async def fill_template_values(
        self, system: str, user: str, tool: dict[str, Any]
    ) -> dict[str, Any]:
        """Forced strict tool-use → a value per template placeholder. The tool
        schema is built per-template from its discovered field names."""
        return await self._tool_call(system, user, tool, TEMPLATE_FILL_MAX_TOKENS)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd server && .venv/bin/python -m pytest tests/test_templates.py -q`
Expected: PASS (9 passed).

- [ ] **Step 6: Commit**

```bash
git add server/app/prompts/template_fill.py server/app/services/generation_service.py server/tests/test_templates.py
git commit -m "feat(templates): dynamic AI-fill tool + fill_template_values"
```

---

### Task 7: Routes — upload / list / delete / ai-fill / render

**Files:**
- Create: `server/app/routes/templates.py`
- Test: `server/tests/test_templates.py`

- [ ] **Step 1: Write the failing route tests** (append to `tests/test_templates.py`)

```python
import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
from app.main import app
from app.models.common import utcnow
from app.models.user import UserInDB
from app.services.generation_service import GenerationService
from app.services.storage_service import get_storage
from app.utils.dependencies import get_current_user
from tests.conftest import TEST_DB_NAME

WS_OID = ObjectId()
OWNER_OID = ObjectId()


class _FakeGen:
    async def fill_template_values(self, system, user, tool):
        return {name: f"draft {name}" for name in tool["input_schema"]["properties"]}


def _user(is_demo: bool = False) -> UserInDB:
    return UserInDB(id=str(OWNER_OID), email="o@example.com", hashed_password="x",
                    full_name="O", is_demo=is_demo)


async def _seed_ws(test_db):
    await test_db.workspaces.insert_one({
        "_id": WS_OID, "owner_id": OWNER_OID, "name": "Verdure", "slug": "verdure",
        "brand_profile": {}, "vector_namespace": str(WS_OID),
        "embedding_model": settings.embedding_model, "embedding_dim": settings.embedding_dim,
        "asset_count": 0, "ready_chunk_count": 0, "created_at": utcnow(), "updated_at": utcnow(),
    })


async def _mk(test_db, tmp_path, monkeypatch, *, is_demo=False) -> AsyncClient:
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    get_storage.cache_clear()
    await _seed_ws(test_db)
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[get_current_user] = lambda: _user(is_demo)
    app.dependency_overrides[GenerationService] = lambda: _FakeGen()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def tpl_client(test_db, tmp_path, monkeypatch):
    ac = await _mk(test_db, tmp_path, monkeypatch)
    async with ac:
        yield ac
    app.dependency_overrides.clear()
    get_storage.cache_clear()


def _base() -> str:
    return f"/api/workspaces/{WS_OID}/templates"


DOCX_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


async def _upload(ac) -> dict:
    data = _docx_bytes("Hello {{client_name}}")
    return (await ac.post(_base(), files={"file": ("Report.docx", data, DOCX_CT)})).json()


@pytest.mark.asyncio
async def test_upload_discovers_and_stores(tpl_client, test_db):
    body = await _upload(tpl_client)
    assert body["format"] == "docx"
    assert body["placeholders"] == ["client_name"]
    assert await get_storage().read(body["storage_key"])  # bytes stored
    assert await test_db.templates.find_one({"_id": ObjectId(body["id"])})


@pytest.mark.asyncio
async def test_upload_rejects_bad_type(tpl_client):
    resp = await tpl_client.post(_base(), files={"file": ("notes.txt", b"hi", "text/plain")})
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_list_and_delete(tpl_client, test_db):
    t = await _upload(tpl_client)
    listed = (await tpl_client.get(_base())).json()
    assert len(listed) == 1
    resp = await tpl_client.delete(f"{_base()}/{t['id']}")
    assert resp.status_code == 200
    assert await test_db.templates.find_one({"_id": ObjectId(t["id"])}) is None


@pytest.mark.asyncio
async def test_ai_fill_returns_values(tpl_client):
    t = await _upload(tpl_client)
    resp = await tpl_client.post(f"{_base()}/{t['id']}/ai-fill", json={"brief": "a welcome letter"})
    assert resp.status_code == 200
    assert resp.json()["values"] == {"client_name": "draft client_name"}


@pytest.mark.asyncio
async def test_render_returns_filled_file(tpl_client):
    t = await _upload(tpl_client)
    resp = await tpl_client.post(f"{_base()}/{t['id']}/render", json={"values": {"client_name": "Acme"}})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == DOCX_CT
    from docx import Document
    text = "\n".join(p.text for p in Document(io.BytesIO(resp.content)).paragraphs)
    assert "Hello Acme" in text


@pytest.mark.asyncio
async def test_upload_demo_blocked(test_db, tmp_path, monkeypatch):
    ac = await _mk(test_db, tmp_path, monkeypatch, is_demo=True)
    async with ac:
        resp = await ac.post(_base(), files={"file": ("Report.docx", _docx_bytes("{{x}}"), DOCX_CT)})
    app.dependency_overrides.clear()
    get_storage.cache_clear()
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_templates.py -q`
Expected: FAIL — 404s (routes not mounted yet).

- [ ] **Step 3: Create `server/app/routes/templates.py`**

```python
"""Template routes (Phase 5). Upload/list/delete branded .docx/.pptx templates,
optionally AI-draft their placeholder values, and render the filled file. Renders
are returned for immediate download — not persisted. The template's styling is
authoritative; we only swap `{{placeholder}}` text."""
from __future__ import annotations

import os

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_database
from app.models.template import (
    TemplateAiFillRequest,
    TemplateAiFillResponse,
    TemplateRenderRequest,
    TemplateResponse,
)
from app.models.user import UserInDB
from app.prompts import template_fill
from app.services import template_service
from app.services.generation_service import GenerationService
from app.services.storage_service import build_template_key, get_storage, safe_filename
from app.utils.dependencies import get_current_user, get_workspace_or_404, require_not_demo

router = APIRouter()

MAX_TEMPLATE_BYTES = 10 * 1024 * 1024  # 10 MB
_FORMAT_BY_EXT = {".docx": "docx", ".pptx": "pptx"}
_MEDIA = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def _resolve_format(filename: str) -> str:
    fmt = _FORMAT_BY_EXT.get(os.path.splitext(filename)[1].lower())
    if not fmt:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported template. Upload a .docx or .pptx file.",
        )
    return fmt


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def upload_template(
    file: UploadFile,
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    filename = file.filename or "template"
    fmt = _resolve_format(filename)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file.")
    if len(data) > MAX_TEMPLATE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Template exceeds the {MAX_TEMPLATE_BYTES // (1024 * 1024)} MB limit.",
        )
    try:
        placeholders = template_service.discover_placeholders(data, fmt)
    except Exception:  # noqa: BLE001 — a corrupt file must not 500
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Couldn't read this template — is it a valid .docx/.pptx?",
        )
    if len(placeholders) > template_service.MAX_PLACEHOLDERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Template has too many fields (max {template_service.MAX_PLACEHOLDERS}).",
        )

    workspace_oid = workspace["_id"]
    template_oid = ObjectId()
    clean_name = safe_filename(filename)
    storage_key = build_template_key(str(workspace_oid), str(template_oid), clean_name)
    await get_storage().save(storage_key, data)
    return await template_service.create_template(
        db, workspace_oid, workspace["owner_id"],
        template_oid=template_oid, name=clean_name, fmt=fmt,
        storage_key=storage_key, placeholders=placeholders,
    )


@router.get("", response_model=list[TemplateResponse])
async def list_templates(
    workspace: dict = Depends(get_workspace_or_404),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    return await template_service.list_templates(db, workspace["_id"])


@router.delete("/{template_id}", status_code=status.HTTP_200_OK)
async def delete_template(
    template_id: str,
    workspace: dict = Depends(get_workspace_or_404),
    _: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    doc = await template_service.get_template(db, workspace["_id"], template_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    await template_service.delete_template(db, doc)
    await get_storage().delete(doc["storage_key"])
    return {"deleted": True}


@router.post("/{template_id}/ai-fill", response_model=TemplateAiFillResponse)
async def ai_fill_template(
    template_id: str,
    payload: TemplateAiFillRequest,
    workspace: dict = Depends(get_workspace_or_404),
    service: GenerationService = Depends(GenerationService),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Draft a value for each placeholder from a brief (optional path). Generative,
    not a mutation → allowed for the demo user. Nothing is persisted."""
    doc = await template_service.get_template(db, workspace["_id"], template_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    placeholders = doc.get("placeholders") or []
    if not placeholders:
        return TemplateAiFillResponse(values={})
    tool = template_fill.build_fill_tool(placeholders)
    result = await service.fill_template_values(
        template_fill.build_fill_system(),
        template_fill.build_fill_user(payload.brief, placeholders),
        tool,
    )
    return TemplateAiFillResponse(values=template_service.clamp_values(result, placeholders))


@router.post("/{template_id}/render")
async def render_template(
    template_id: str,
    payload: TemplateRenderRequest,
    workspace: dict = Depends(get_workspace_or_404),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Fill the template with the given values and return the file for download.
    Ownership via the dependency; the template's storage key is rebuilt server-side."""
    doc = await template_service.get_template(db, workspace["_id"], template_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    fmt = doc["format"]
    key = build_template_key(str(workspace["_id"]), template_id, doc["name"])
    try:
        data = await get_storage().read(key)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template file missing")
    values = template_service.clamp_values(payload.values, doc.get("placeholders") or [])
    filled = template_service.render(data, values, fmt)
    out_name = safe_filename(f"{os.path.splitext(doc['name'])[0]}-filled.{fmt}")
    return Response(
        content=filled,
        media_type=_MEDIA[fmt],
        headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
    )
```

- [ ] **Step 4: Mount the router** in `server/app/main.py`

Add `templates` to the routes import (the `from app.routes import (...)` block):

```python
    templates,
```

Add the mount (next to the assets mount):

```python
app.include_router(
    templates.router, prefix="/api/workspaces/{workspace_id}/templates", tags=["templates"]
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_templates.py -q`
Expected: PASS (all template tests).

- [ ] **Step 6: Commit**

```bash
git add server/app/routes/templates.py server/app/main.py server/tests/test_templates.py
git commit -m "feat(templates): upload/list/delete/ai-fill/render routes"
```

---

### Task 8: Workspace-delete cascade + index

**Files:**
- Modify: `server/app/services/workspace_service.py`
- Modify: `server/app/database.py`

- [ ] **Step 1: Drop templates on workspace delete** — in `delete_workspace` (`workspace_service.py`), alongside the existing `assets`/`generations` deletes, add:

```python
    await db.templates.delete_many({"workspace_id": oid})
```

- [ ] **Step 2: Add the index** — in `server/app/database.py` `ensure_indexes()`, alongside the existing `create_index` calls, add:

```python
    await db.templates.create_index("workspace_id")
```

- [ ] **Step 3: Run the full server suite**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest -q`
Expected: PASS (all).

- [ ] **Step 4: Commit**

```bash
git add server/app/services/workspace_service.py server/app/database.py
git commit -m "feat(templates): drop templates on workspace delete + index"
```

---

### Task 9: Server gate

**Files:** none (verification)

- [ ] **Step 1: ruff + mypy + pytest**

Run: `cd server && .venv/bin/ruff check app tests && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/mypy app && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest -q`
Expected: ruff clean; mypy clean; all tests pass.

- [ ] **Step 2: Fix anything; commit if changed**

```bash
git add -A && git commit -m "chore(templates): server gate green"
```

(Skip if nothing changed.)

---

### Task 10: Client — types + API

**Files:**
- Modify: `client/src/types/index.ts`
- Create: `client/src/api/templates.ts`

- [ ] **Step 1: Add types** to `client/src/types/index.ts` (after the document types):

```typescript
export type TemplateFormat = "docx" | "pptx";

export interface Template {
  id: string;
  workspace_id: string;
  name: string;
  format: TemplateFormat;
  storage_key: string;
  placeholders: string[];
  created_at: string | null;
}
```

- [ ] **Step 2: Create `client/src/api/templates.ts`**

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { downloadBlob } from "@/features/generate/useCardExport";
import { api } from "@/lib/api";
import type { Template } from "@/types";

export function useTemplates(workspaceId: string | null) {
  return useQuery({
    queryKey: ["templates", workspaceId],
    enabled: !!workspaceId,
    queryFn: async () =>
      (await api.get<Template[]>(`/workspaces/${workspaceId}/templates`)).data,
  });
}

export function useUploadTemplate(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return (await api.post<Template>(`/workspaces/${workspaceId}/templates`, form)).data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["templates", workspaceId] }),
  });
}

export function useDeleteTemplate(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (templateId: string) => {
      await api.delete(`/workspaces/${workspaceId}/templates/${templateId}`);
      return templateId;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["templates", workspaceId] }),
  });
}

export function useAiFillTemplate(workspaceId: string | null) {
  return useMutation({
    mutationFn: async (input: { templateId: string; brief: string }) =>
      (
        await api.post<{ values: Record<string, string> }>(
          `/workspaces/${workspaceId}/templates/${input.templateId}/ai-fill`,
          { brief: input.brief },
        )
      ).data.values,
  });
}

/** Render a template with values and trigger a file download. */
export async function renderTemplate(
  workspaceId: string,
  template: Template,
  values: Record<string, string>,
): Promise<void> {
  const resp = await api.post(
    `/workspaces/${workspaceId}/templates/${template.id}/render`,
    { values },
    { responseType: "blob" },
  );
  const base = template.name.replace(/\.(docx|pptx)$/i, "");
  downloadBlob(resp.data as Blob, `${base}-filled.${template.format}`);
}
```

- [ ] **Step 3: Typecheck**

Run: `cd client && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add client/src/types/index.ts client/src/api/templates.ts
git commit -m "feat(templates): client types + API"
```

---

### Task 11: Client — fill-form helpers + test

**Files:**
- Create: `client/src/features/templates/templateForm.ts`
- Test: `client/src/features/templates/templateForm.test.ts`

- [ ] **Step 1: Write the failing test**

Create `client/src/features/templates/templateForm.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { emptyValues, mergeFilled } from "./templateForm";

describe("template fill form (Phase 5)", () => {
  it("initializes an empty value per placeholder", () => {
    expect(emptyValues(["title", "body"])).toEqual({ title: "", body: "" });
  });
  it("merges AI-filled values only for known placeholders", () => {
    const merged = mergeFilled(["title", "body"], { title: "Hi", extra: "x" });
    expect(merged).toEqual({ title: "Hi", body: "" });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/features/templates/templateForm.test.ts`
Expected: FAIL — cannot find module `./templateForm`.

- [ ] **Step 3: Create `client/src/features/templates/templateForm.ts`**

```typescript
/** A blank value for each placeholder. */
export function emptyValues(placeholders: string[]): Record<string, string> {
  return Object.fromEntries(placeholders.map((p) => [p, ""]));
}

/** Apply filled values (e.g. an AI draft) onto the known placeholders only,
 *  leaving unknown keys out and missing ones blank. */
export function mergeFilled(
  placeholders: string[],
  filled: Record<string, string>,
): Record<string, string> {
  return Object.fromEntries(placeholders.map((p) => [p, filled[p] ?? ""]));
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/features/templates/templateForm.test.ts`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add client/src/features/templates/templateForm.ts client/src/features/templates/templateForm.test.ts
git commit -m "feat(templates): fill-form value helpers + test"
```

---

### Task 12: Client — Templates page + nav + route

**Files:**
- Create: `client/src/features/templates/TemplatesPage.tsx`
- Modify: `client/src/components/layout/SideNav.tsx`, `client/src/App.tsx`

- [ ] **Step 1: Create `client/src/features/templates/TemplatesPage.tsx`**

```tsx
import { useRef, useState } from "react";
import { FileText, Sparkles, Trash2, Upload } from "lucide-react";
import { useDeleteTemplate, useTemplates, useUploadTemplate, useAiFillTemplate, renderTemplate } from "@/api/templates";
import { DemoNotice } from "@/components/DemoNotice";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useActiveWorkspace } from "@/features/workspace/useActiveWorkspace";
import { useAuthStore } from "@/stores/auth";
import type { Template } from "@/types";
import { emptyValues, mergeFilled } from "./templateForm";

export function TemplatesPage() {
  const { workspaceId } = useActiveWorkspace();
  const isDemo = useAuthStore((s) => s.user?.is_demo ?? false);
  const { data: templates } = useTemplates(workspaceId);
  const upload = useUploadTemplate(workspaceId);
  const del = useDeleteTemplate(workspaceId);
  const fileRef = useRef<HTMLInputElement>(null);
  const [active, setActive] = useState<Template | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setError(null);
    try {
      await upload.mutateAsync(file);
    } catch {
      setError("Couldn’t upload — use a .docx or .pptx under 10 MB.");
    }
  }

  return (
    <div className="flex max-w-3xl flex-col gap-8">
      <header className="animate-fade-in-up">
        <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
          Templates
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-[-0.01em] text-foreground">
          On-brand templates
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Upload a branded .docx or .pptx with {"{{placeholders}}"} — fill it with your own text (or
          an AI draft) and download a file in your template’s exact styling.
        </p>
      </header>

      {isDemo && (
        <DemoNotice message="You're exploring as a demo — uploading and deleting templates is disabled so the seeded workspace stays intact." />
      )}

      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">Your templates</h2>
          <input
            ref={fileRef}
            type="file"
            accept=".docx,.pptx"
            className="hidden"
            onChange={onFile}
          />
          <Button
            size="sm"
            variant="secondary"
            onClick={() => fileRef.current?.click()}
            loading={upload.isPending}
            disabled={isDemo}
            title={isDemo ? "Disabled in the demo" : undefined}
          >
            <Upload className="h-4 w-4" aria-hidden />
            Upload template
          </Button>
        </div>
        {error && <span className="text-xs text-destructive">{error}</span>}
        {(templates ?? []).length === 0 ? (
          <div className="rounded-lg border border-dashed border-border bg-surface p-8 text-center text-sm text-muted-foreground">
            No templates yet. Upload a branded .docx or .pptx to start.
          </div>
        ) : (
          <ul className="flex flex-col divide-y divide-border rounded-xl border border-border bg-surface">
            {(templates ?? []).map((t) => (
              <li key={t.id} className="flex items-center gap-3 px-4 py-3">
                <FileText className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                <div className="flex min-w-0 flex-col leading-tight">
                  <span className="truncate text-sm font-medium text-foreground">{t.name}</span>
                  <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
                    {t.format} · {t.placeholders.length} field{t.placeholders.length === 1 ? "" : "s"}
                  </span>
                </div>
                <div className="ml-auto flex items-center gap-1">
                  <Button size="sm" onClick={() => setActive(t)}>
                    Use
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={() => del.mutate(t.id)}
                    disabled={isDemo}
                    title={isDemo ? "Disabled in the demo" : "Delete"}
                    aria-label="Delete template"
                    className="hover:text-destructive"
                  >
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {active && (
        <FillPanel
          key={active.id}
          workspaceId={workspaceId}
          template={active}
          onClose={() => setActive(null)}
        />
      )}
    </div>
  );
}

function FillPanel({
  workspaceId,
  template,
  onClose,
}: {
  workspaceId: string | null;
  template: Template;
  onClose: () => void;
}) {
  const aiFill = useAiFillTemplate(workspaceId);
  const [values, setValues] = useState<Record<string, string>>(() => emptyValues(template.placeholders));
  const [brief, setBrief] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function draftWithAI() {
    if (!brief.trim()) return;
    setError(null);
    try {
      const filled = await aiFill.mutateAsync({ templateId: template.id, brief });
      setValues(mergeFilled(template.placeholders, filled));
    } catch {
      setError("AI draft failed — fill the fields yourself or try again.");
    }
  }

  async function download() {
    if (!workspaceId) return;
    setDownloading(true);
    setError(null);
    try {
      await renderTemplate(workspaceId, template, values);
    } catch {
      setError("Couldn’t render the file. Try again.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <section className="flex flex-col gap-4 rounded-xl border border-border bg-surface p-5 shadow-light">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">Fill “{template.name}”</h2>
        <Button size="sm" variant="ghost" onClick={onClose}>
          Close
        </Button>
      </div>

      {template.placeholders.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          This template has no {"{{placeholders}}"} — downloading returns it unchanged.
        </p>
      ) : (
        <>
          <div className="flex flex-col gap-2 rounded-lg border border-dashed border-border bg-surface-variant/40 p-3.5">
            <Label htmlFor="tpl-brief">Draft with AI (optional)</Label>
            <Textarea
              id="tpl-brief"
              rows={2}
              placeholder="e.g. a welcome letter for a new hempcrete supplier"
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
            />
            <div>
              <Button size="sm" variant="secondary" onClick={draftWithAI} loading={aiFill.isPending}>
                <Sparkles className="h-4 w-4" aria-hidden />
                Draft with AI
              </Button>
            </div>
          </div>

          <div className="flex flex-col gap-3">
            {template.placeholders.map((p) => (
              <div key={p} className="flex flex-col">
                <Label htmlFor={`f-${p}`}>{p}</Label>
                <Input
                  id={`f-${p}`}
                  value={values[p] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [p]: e.target.value }))}
                />
              </div>
            ))}
          </div>
        </>
      )}

      {error && <span className="text-xs text-destructive">{error}</span>}
      <div>
        <Button onClick={download} loading={downloading}>
          Download {template.format.toUpperCase()}
        </Button>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Add the nav item** in `client/src/components/layout/SideNav.tsx`

Add `LayoutTemplate` to the lucide import, and a `NAV` entry after Assets:

```typescript
  { to: "/templates", label: "Templates", icon: LayoutTemplate },
```

- [ ] **Step 3: Add the route** in `client/src/App.tsx`

Import and add the route alongside the others:

```tsx
import { TemplatesPage } from "@/features/templates/TemplatesPage";
```

```tsx
        <Route path="templates" element={<TemplatesPage />} />
```

- [ ] **Step 4: Typecheck + lint + format**

Run: `cd client && npx tsc --noEmit && npx eslint src && npx prettier --write "src/**/*.{ts,tsx}"`
Expected: tsc + eslint clean; prettier writes.

- [ ] **Step 5: Commit**

```bash
git add client/src/features/templates/TemplatesPage.tsx client/src/components/layout/SideNav.tsx client/src/App.tsx
git commit -m "feat(templates): Templates page + nav + route"
```

---

### Task 13: Client gate

**Files:** none (verification)

- [ ] **Step 1: tsc + eslint + prettier + vitest + build**

Run: `cd client && npx tsc --noEmit && npx eslint src && npx prettier --check "src/**/*.{ts,tsx}" && npx vitest run && npx vite build`
Expected: all green.

- [ ] **Step 2: Fix anything; commit if changed**

```bash
git add -A && git commit -m "chore(templates): client gate green"
```

(Skip if nothing changed.)

---

### Task 14: Docs

**Files:** `docs/DECISIONS.md`, `docs/PLAN.md`, `CHANGELOG.md`, `docs/DESIGN.md`

- [ ] **Step 1: DECISIONS** — add entry #24: Phase 5 on-brand templates — upload `.docx`/`.pptx` with `{{placeholders}}`; **template styling authoritative** (fill text only, no `brand_profile` injection); dynamic discover-then-fill (docxtpl for docx, paragraph-level replace for pptx); primary = user's own text, optional = one AI tool-use draft; own `templates` collection + Templates page; **not Assets** (never ingested); renders ephemeral; **card presets split to PR-B**; style-extraction fallback for untagged templates deferred.

- [ ] **Step 2: PLAN.md** — under "Phase 5 — On-brand templates", note PR-A (document templates) built; PR-B (custom card presets) pending.

- [ ] **Step 3: CHANGELOG.md** — add a "Phase 5: On-brand templates — `0.7.0` *(PR-A: document templates)*" subsection under `[Unreleased]`: routes (upload/list/delete/ai-fill/render), docx via docxtpl + pptx paragraph-replace, styling authoritative, Templates page, tests (pytest +N, vitest +N), dep docxtpl.

- [ ] **Step 4: DESIGN.md** — add a "Templates page (Phase 5)" note: nav entry; list/upload/delete; a fill view with a field per placeholder + optional "Draft with AI" + Download; the pptx run-splitting fidelity caveat; demo read-only via `DemoNotice`.

- [ ] **Step 5: Commit**

```bash
git add docs/DECISIONS.md docs/PLAN.md CHANGELOG.md docs/DESIGN.md
git commit -m "docs(phase-5): on-brand templates — DECISIONS/PLAN/CHANGELOG/DESIGN"
```

---

### Task 15: Review gate, live verify, PR

**Files:** none (process)

- [ ] **Step 1: Re-run both gates** (Task 9 + Task 13 commands) — confirm green.
- [ ] **Step 2: `/code-review`** on the branch diff; fix real findings.
- [ ] **Step 3: `/security-review`**; fix real findings. New surface: parsing/rendering untrusted Office files (docxtpl/python-pptx) — size-capped; docxtpl renders Jinja with a plain context (no template-injection from user *values* — values are data, not template source; only the uploaded template is the Jinja source, and it's owner-only/demo-blocked); ownership + demo guards on mutations; render reads a server-derived key.
- [ ] **Step 4: Live verify (owner):** upload a branded `.docx` + a `.pptx` with `{{tags}}`, fill with your own text, download, open in Word/PowerPoint and confirm styling is intact and text substituted; try "Draft with AI"; delete; confirm demo read-only.
- [ ] **Step 5: Owner commit/push approval**, then push `feat/5-templates` and open a PR into `dev` (GitHub REST API + keychain token; no `gh`). Update `bcs-phase-state` memory when it merges.

---

## Self-Review

**Spec coverage:** both docx+pptx (Tasks 2,3) ✓; styling authoritative / no brand injection (render swaps text only, Task 3) ✓; dynamic discover-then-fill (Tasks 2,6) ✓; manual primary + AI optional (Tasks 7,12) ✓; own `templates` collection, not Assets (Tasks 5,8) ✓; renders ephemeral (render route returns bytes, Task 7) ✓; Templates nav page (Task 12) ✓; caps `MAX_PLACEHOLDERS`/`MAX_VALUE_LEN` (Tasks 3,7) ✓; pptx run-split handling (Task 3) ✓; errors 400/413/415/422 + demo guard (Task 7) ✓; docxtpl dep (Task 1) ✓; tests pytest+vitest (throughout) ✓; docs (Task 14) ✓.

**Placeholder scan:** none — every code step has full code; doc steps (Task 14) describe concrete edits mirroring existing entries.

**Type consistency:** `TemplateResponse{id,workspace_id,name,format,storage_key,placeholders,created_at}` matches server model (Task 4), CRUD (Task 5), route returns (Task 7), client `Template` type (Task 10). `render(data, values, fmt)` / `discover_placeholders(data, fmt)` / `clamp_values(values, placeholders)` signatures match call sites (Tasks 3,7). `fill_template_values(system, user, tool)` matches the fake (Task 7) and route call (Task 7). `build_fill_tool(placeholders)` shape matches the test (Task 6) and route (Task 7). Client `emptyValues`/`mergeFilled` (Task 11) match `TemplatesPage` usage (Task 12). `downloadBlob` reused from `useCardExport` (Task 10).
