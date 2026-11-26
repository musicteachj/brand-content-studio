# Example-Card Exemplar Steering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an owner upload past on-brand cards; pre-extract a short text "style note" from each via Claude vision, store them on the workspace, and inject them into the text/card/post generation prompts so new copy steers toward the brand's own examples.

**Architecture:** Reuse the logo + 4c-extract patterns. Upload → one forced strict Claude-vision tool-use call returns a `style_note` → store image bytes via `StorageBackend` + `$push` a `BrandExemplar` onto `brand_profile.exemplars` (cap 5). At generation, join the notes and append them as a trusted block in the existing `build_system(...)` seam (where `voice_summary` already lands). Honesty: approximate via our Satori archetypes, never pixel-clone.

**Tech Stack:** FastAPI + Motor + Pydantic v2 + Pillow/AsyncAnthropic (server); React + Vite + TS + react-query + Zustand (client). Tests: pytest + vitest.

**Spec:** `docs/superpowers/specs/2026-06-26-exemplar-steering-design.md`

**Working dir for server commands:** `server/`. Run pytest/ruff/mypy via the venv: `.venv/bin/...`, and prefix model-touching runs with `env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY` (the shell shadows the key). Branch: `feat/4c-exemplars` (already created off `dev`).

**File structure (created/modified):**
- Create `server/app/prompts/exemplars.py` — `build_exemplar_guidance(notes)` (pure prompt-block builder).
- Modify `server/app/prompts/text_post.py`, `server/app/prompts/image_card.py` — optional `exemplar_guidance` arg on the system builders.
- Modify `server/app/prompts/brand_extract.py` — `EXEMPLAR_NOTE_TOOL` + exemplar prompt builders.
- Modify `server/app/services/brand_extract_service.py` — parameterize `_vision_tool_call(tool=...)`; add `propose_exemplar_note`.
- Modify `server/app/models/common.py` — `BrandExemplar` + `BrandProfile.exemplars`.
- Modify `server/app/services/workspace_service.py` — `MAX_EXEMPLARS`, `add_workspace_exemplar`, `remove_workspace_exemplar`.
- Modify `server/app/routes/workspaces.py` — `POST`/`DELETE /workspaces/{id}/exemplars`.
- Modify `server/app/routes/generate.py` — build + pass `exemplar_guidance` in /text, /card, /post.
- Create `server/tests/test_exemplars.py`; modify `server/tests/test_generate_route.py`.
- Modify `client/src/types/index.ts`, `client/src/api/workspaces.ts`.
- Create `client/src/features/settings/exemplars.ts` (+ `.test.ts`), `client/src/features/settings/ExemplarsSection.tsx`; modify `client/src/features/settings/SettingsPage.tsx`.
- Docs: `docs/DECISIONS.md`, `docs/phase-4-plan.md`, `CHANGELOG.md`, `docs/DESIGN.md`.

---

### Task 1: `build_exemplar_guidance` prompt-block builder

**Files:**
- Create: `server/app/prompts/exemplars.py`
- Test: `server/tests/test_exemplars.py`

- [ ] **Step 1: Write the failing test**

Create `server/tests/test_exemplars.py`:

```python
"""Exemplar steering (Phase 4c PR-C): the prompt-guidance builder is pure; the
extraction + routes are tested with the vision service faked (no model call)."""
from app.prompts.exemplars import build_exemplar_guidance


def test_build_exemplar_guidance_joins_notes():
    out = build_exemplar_guidance(["Punchy hook, short body.", "Earthy photography, lots of negative space."])
    assert out is not None
    assert "1. Punchy hook, short body." in out
    assert "2. Earthy photography, lots of negative space." in out
    assert "do not copy their exact words" in out.lower()


def test_build_exemplar_guidance_empty_returns_none():
    assert build_exemplar_guidance([]) is None
    assert build_exemplar_guidance(["", "   "]) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && .venv/bin/python -m pytest tests/test_exemplars.py -q`
Expected: FAIL — `ModuleNotFoundError: app.prompts.exemplars`.

- [ ] **Step 3: Write the implementation**

Create `server/app/prompts/exemplars.py`:

```python
"""Exemplar steering (Phase 4c). Joins the per-exemplar style notes into a single
trusted instruction block appended to the generation system prompt — the same
seam as `voice_summary`. The notes are the owner's own derived brand guidance, so
they are instructions to follow (not untrusted retrieved data)."""
from __future__ import annotations


def build_exemplar_guidance(notes: list[str]) -> str | None:
    """A trusted 'examples to emulate' block, or None when there are no notes."""
    clean = [n.strip() for n in notes if n and n.strip()]
    if not clean:
        return None
    lines = [
        "On-brand examples to emulate (the brand's own past cards — match their "
        "style and patterns, but do not copy their exact words):"
    ]
    for i, note in enumerate(clean, start=1):
        lines.append(f"{i}. {note}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && .venv/bin/python -m pytest tests/test_exemplars.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add server/app/prompts/exemplars.py server/tests/test_exemplars.py
git commit -m "feat(exemplars): build_exemplar_guidance prompt-block builder"
```

---

### Task 2: Thread `exemplar_guidance` into the system builders

**Files:**
- Modify: `server/app/prompts/text_post.py` (`build_system`)
- Modify: `server/app/prompts/image_card.py` (`build_copy_system`)
- Test: `server/tests/test_exemplars.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_exemplars.py`)

```python
from app.prompts import image_card, text_post


def test_text_post_system_appends_exemplar_block():
    g = "On-brand examples to emulate (the brand's own past cards...):\n1. Punchy."
    sys_with = text_post.build_system("Grounded voice.", g)
    assert "Punchy." in sys_with
    sys_without = text_post.build_system("Grounded voice.")
    assert "Punchy." not in sys_without


def test_card_copy_system_appends_exemplar_block():
    g = "examples...\n1. Earthy."
    assert "Earthy." in image_card.build_copy_system("V", g)
    assert "Earthy." not in image_card.build_copy_system("V")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && .venv/bin/python -m pytest tests/test_exemplars.py -q`
Expected: FAIL — `build_system() takes 1 positional argument but 2 were given`.

- [ ] **Step 3: Edit `text_post.build_system`** (`server/app/prompts/text_post.py`)

Replace the existing `build_system`:

```python
def build_system(voice_summary: str | None, exemplar_guidance: str | None = None) -> str:
    system = _SYSTEM_BASE
    if voice_summary:
        system += f"\n\nBrand voice summary (authoritative):\n{voice_summary.strip()}"
    if exemplar_guidance:
        system += f"\n\n{exemplar_guidance}"
    return system
```

- [ ] **Step 4: Edit `image_card.build_copy_system`** (`server/app/prompts/image_card.py`)

Replace the existing `build_copy_system`:

```python
def build_copy_system(voice_summary: str | None, exemplar_guidance: str | None = None) -> str:
    system = _COPY_SYSTEM
    if voice_summary:
        system += f"\n\nBrand voice summary (authoritative):\n{voice_summary.strip()}"
    if exemplar_guidance:
        system += f"\n\n{exemplar_guidance}"
    return system
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd server && .venv/bin/python -m pytest tests/test_exemplars.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add server/app/prompts/text_post.py server/app/prompts/image_card.py server/tests/test_exemplars.py
git commit -m "feat(exemplars): optional exemplar_guidance in text/card system prompts"
```

---

### Task 3: `BrandExemplar` model + `BrandProfile.exemplars`

**Files:**
- Modify: `server/app/models/common.py`
- Test: `server/tests/test_exemplars.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_exemplars.py`)

```python
from app.models.common import BrandExemplar, BrandProfile


def test_brand_profile_exemplars_default_empty():
    assert BrandProfile().exemplars == []


def test_brand_exemplar_shape():
    e = BrandExemplar(id="abc", storage_key="ws/images/abc/c.png", url="/u", style_note="Punchy.")
    assert e.id == "abc" and e.style_note == "Punchy."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && .venv/bin/python -m pytest tests/test_exemplars.py -q`
Expected: FAIL — `ImportError: cannot import name 'BrandExemplar'`.

- [ ] **Step 3: Edit `server/app/models/common.py`**

Add after the `BrandLogo` class:

```python
class BrandExemplar(BaseModel):
    """A past on-brand card the owner uploaded; we store the image + a short
    extracted style note that steers generation (Phase 4c)."""

    id: str
    storage_key: str
    url: Optional[str] = None
    style_note: str
```

Add `exemplars` to `BrandProfile` (after the `logo` field):

```python
    exemplars: list[BrandExemplar] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && .venv/bin/python -m pytest tests/test_exemplars.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add server/app/models/common.py server/tests/test_exemplars.py
git commit -m "feat(exemplars): BrandExemplar model + BrandProfile.exemplars"
```

---

### Task 4: Exemplar extraction — vision tool + service method

**Files:**
- Modify: `server/app/prompts/brand_extract.py`
- Modify: `server/app/services/brand_extract_service.py`
- Test: `server/tests/test_exemplars.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_exemplars.py`)

```python
from app.prompts.brand_extract import EXEMPLAR_NOTE_TOOL, build_exemplar_system, build_exemplar_user


def test_exemplar_note_tool_schema():
    assert EXEMPLAR_NOTE_TOOL["name"] == "exemplar_note"
    assert EXEMPLAR_NOTE_TOOL["strict"] is True
    assert EXEMPLAR_NOTE_TOOL["input_schema"]["required"] == ["style_note"]


def test_exemplar_prompt_builders_nonempty():
    assert "do not" in build_exemplar_system().lower()  # the no-clone instruction
    assert build_exemplar_user().strip()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && .venv/bin/python -m pytest tests/test_exemplars.py -q`
Expected: FAIL — `ImportError: cannot import name 'EXEMPLAR_NOTE_TOOL'`.

- [ ] **Step 3: Edit `server/app/prompts/brand_extract.py`** — append:

```python
_EXEMPLAR_SYSTEM = """You are a brand designer studying one of a brand's own past social cards (the attached image). In 1-3 sentences, describe the STYLE to emulate when writing new on-brand cards: the copy patterns (hook, rhythm, length, diction, how the CTA reads) and the visual direction (mood, composition, imagery). Describe patterns to emulate through our own card templates — do NOT instruct a pixel-faithful copy of this exact layout, and do not invent facts. Call the exemplar_note tool with one concise note."""


def build_exemplar_system() -> str:
    return _EXEMPLAR_SYSTEM


def build_exemplar_user() -> str:
    return "Study the attached brand card and record a concise style note to emulate in future cards."


EXEMPLAR_NOTE_TOOL = {
    "name": "exemplar_note",
    "description": "Record a concise style note (copy + visual direction) to emulate from a past brand card.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "style_note": {
                "type": "string",
                "description": "1-3 sentences on the copy patterns and visual direction to emulate.",
            }
        },
        "required": ["style_note"],
    },
}
```

- [ ] **Step 4: Edit `server/app/services/brand_extract_service.py`**

Parameterize `_vision_tool_call` to take the tool. Change its signature and the two references:

```python
    async def _vision_tool_call(
        self, system: str, user: str, image_b64: str, media_type: str, tool: dict[str, Any]
    ) -> dict[str, Any]:
```

In the `messages.create(...)` call inside it, replace `BRAND_EXTRACT_TOOL` with `tool` in both the `tools=[...]` and `tool_choice=...` lines:

```python
            tools=[cast(ToolParam, tool)],
            tool_choice=cast(ToolChoiceToolParam, {"type": "tool", "name": tool["name"]}),
```

And update the final error string:

```python
        raise RuntimeError(f"Model did not return the {tool['name']} tool call.")
```

Update the existing `propose` to pass the tool:

```python
        result = await self._vision_tool_call(
            system=build_extract_system(),
            user=build_extract_user(detected),
            image_b64=base64.standard_b64encode(data).decode("ascii"),
            media_type=media_type,
            tool=BRAND_EXTRACT_TOOL,
        )
```

Add the new method on `BrandExtractService` (below `propose`):

```python
    async def propose_exemplar_note(self, data: bytes, media_type: str) -> str:
        """One vision tool-use call → a short style note for an uploaded card."""
        result = await self._vision_tool_call(
            system=build_exemplar_system(),
            user=build_exemplar_user(),
            image_b64=base64.standard_b64encode(data).decode("ascii"),
            media_type=media_type,
            tool=EXEMPLAR_NOTE_TOOL,
        )
        return str(result.get("style_note", "")).strip()
```

Update the import at the top of the file:

```python
from app.prompts.brand_extract import (
    BRAND_EXTRACT_TOOL,
    EXEMPLAR_NOTE_TOOL,
    build_exemplar_system,
    build_exemplar_user,
    build_extract_system,
    build_extract_user,
)
```

- [ ] **Step 5: Run tests to verify pass (incl. existing extract tests still green)**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_exemplars.py tests/test_brand_extract.py -q`
Expected: PASS (8 + 9).

- [ ] **Step 6: Commit**

```bash
git add server/app/prompts/brand_extract.py server/app/services/brand_extract_service.py server/tests/test_exemplars.py
git commit -m "feat(exemplars): vision exemplar_note tool + propose_exemplar_note service"
```

---

### Task 5: workspace_service add/remove exemplar

**Files:**
- Modify: `server/app/services/workspace_service.py`
- (Covered by the route tests in Task 6 — no separate unit test.)

- [ ] **Step 1: Edit `server/app/services/workspace_service.py`**

Update the import to include `BrandExemplar`:

```python
from app.models.common import BrandExemplar, BrandLogo, serialize_doc, utcnow
```

Add a module constant near the top (after `_SLUG_STRIP`):

```python
MAX_EXEMPLARS = 5
```

Add two functions (next to `set_workspace_logo`):

```python
async def add_workspace_exemplar(
    db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str, exemplar: BrandExemplar
) -> Optional[WorkspaceResponse]:
    """Append an exemplar to `brand_profile.exemplars` (targeted $push)."""
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    if not doc:
        return None
    now = utcnow()
    await db.workspaces.update_one(
        {"_id": doc["_id"]},
        {"$push": {"brand_profile.exemplars": exemplar.model_dump()}, "$set": {"updated_at": now}},
    )
    bp = doc.setdefault("brand_profile", {})
    bp.setdefault("exemplars", []).append(exemplar.model_dump())
    doc["updated_at"] = now
    return _to_response(doc)


async def remove_workspace_exemplar(
    db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str, exemplar_id: str
) -> Optional[tuple[WorkspaceResponse, Optional[str]]]:
    """Pull an exemplar by id; return the updated workspace + its storage key
    (so the caller can delete the bytes), or None if not owned."""
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    if not doc:
        return None
    exemplars = (doc.get("brand_profile") or {}).get("exemplars") or []
    old_key = next((e.get("storage_key") for e in exemplars if e.get("id") == exemplar_id), None)
    now = utcnow()
    await db.workspaces.update_one(
        {"_id": doc["_id"]},
        {"$pull": {"brand_profile.exemplars": {"id": exemplar_id}}, "$set": {"updated_at": now}},
    )
    bp = doc.setdefault("brand_profile", {})
    bp["exemplars"] = [e for e in exemplars if e.get("id") != exemplar_id]
    doc["updated_at"] = now
    return _to_response(doc), old_key
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `cd server && .venv/bin/ruff check app/services/workspace_service.py && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/mypy app/services/workspace_service.py`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add server/app/services/workspace_service.py
git commit -m "feat(exemplars): add/remove workspace exemplar service fns"
```

---

### Task 6: Routes — POST/DELETE exemplars

**Files:**
- Modify: `server/app/routes/workspaces.py`
- Test: `server/tests/test_exemplars.py`

- [ ] **Step 1: Write the failing route tests** (append to `tests/test_exemplars.py`)

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
from app.services.brand_extract_service import BrandExtractService
from app.services.storage_service import get_storage
from app.utils.dependencies import get_current_user
from tests.conftest import TEST_DB_NAME

WS_OID = ObjectId()
OWNER_OID = ObjectId()
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000a49444154789c6360000002000154a24f3f0000000049454e44ae426082"
)


class _FakeExtract:
    async def propose_exemplar_note(self, data: bytes, media_type: str) -> str:
        return "Punchy hook, one tight line, earthy photography."


def _user(is_demo: bool = False) -> UserInDB:
    return UserInDB(id=str(OWNER_OID), email="o@example.com", hashed_password="x",
                    full_name="O", is_demo=is_demo)


async def _seed(test_db, exemplars=None):
    await test_db.workspaces.insert_one({
        "_id": WS_OID, "owner_id": OWNER_OID, "name": "Verdure", "slug": "verdure",
        "brand_profile": {"colors": [], "exemplars": exemplars or []},
        "vector_namespace": str(WS_OID), "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim, "asset_count": 0, "ready_chunk_count": 0,
        "created_at": utcnow(), "updated_at": utcnow(),
    })


async def _mk(test_db, tmp_path, monkeypatch, *, is_demo=False, exemplars=None):
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    get_storage.cache_clear()
    await _seed(test_db, exemplars)
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[get_current_user] = lambda: _user(is_demo)
    app.dependency_overrides[BrandExtractService] = lambda: _FakeExtract()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def ex_client(test_db, tmp_path, monkeypatch):
    ac = await _mk(test_db, tmp_path, monkeypatch)
    async with ac:
        yield ac
    app.dependency_overrides.clear()
    get_storage.cache_clear()


def _url() -> str:
    return f"/api/workspaces/{WS_OID}/exemplars"


@pytest.mark.asyncio
async def test_add_exemplar_appends_and_stores(ex_client, test_db):
    resp = await ex_client.post(_url(), files={"file": ("card.png", PNG, "image/png")})
    assert resp.status_code == 200
    exemplars = resp.json()["brand_profile"]["exemplars"]
    assert len(exemplars) == 1
    assert exemplars[0]["style_note"].startswith("Punchy hook")
    assert exemplars[0]["storage_key"].startswith(f"{WS_OID}/images/")
    assert await get_storage().read(exemplars[0]["storage_key"]) == PNG


@pytest.mark.asyncio
async def test_add_exemplar_rejects_bad_type(ex_client):
    resp = await ex_client.post(_url(), files={"file": ("c.txt", b"hi", "text/plain")})
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_add_exemplar_enforces_cap(test_db, tmp_path, monkeypatch):
    full = [{"id": str(ObjectId()), "storage_key": f"k{i}", "url": None, "style_note": "n"} for i in range(5)]
    ac = await _mk(test_db, tmp_path, monkeypatch, exemplars=full)
    async with ac:
        resp = await ac.post(_url(), files={"file": ("card.png", PNG, "image/png")})
    app.dependency_overrides.clear()
    get_storage.cache_clear()
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_add_exemplar_demo_blocked(test_db, tmp_path, monkeypatch):
    ac = await _mk(test_db, tmp_path, monkeypatch, is_demo=True)
    async with ac:
        resp = await ac.post(_url(), files={"file": ("card.png", PNG, "image/png")})
    app.dependency_overrides.clear()
    get_storage.cache_clear()
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_exemplar_pulls_and_removes_bytes(ex_client, test_db):
    add = await ex_client.post(_url(), files={"file": ("card.png", PNG, "image/png")})
    ex = add.json()["brand_profile"]["exemplars"][0]
    resp = await ex_client.delete(f"{_url()}/{ex['id']}")
    assert resp.status_code == 200
    assert resp.json()["brand_profile"]["exemplars"] == []
    import pytest as _pt
    with _pt.raises(FileNotFoundError):
        await get_storage().read(ex["storage_key"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_exemplars.py -q`
Expected: FAIL — 404s (routes not defined yet).

- [ ] **Step 3: Edit `server/app/routes/workspaces.py`**

Update imports — add `BrandExemplar` to the `app.models.common` import, and `MAX_EXEMPLARS` to the workspace_service usage:

```python
from app.models.common import BrandExemplar, BrandLogo
```

```python
from app.services.workspace_service import MAX_EXEMPLARS
```

Add the two routes (place them just before `@router.delete("/{workspace_id}", ...)`):

```python
@router.post("/{workspace_id}/exemplars", response_model=WorkspaceResponse)
async def add_exemplar(
    file: UploadFile,
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
    service: BrandExtractService = Depends(BrandExtractService),
):
    """Upload a past brand card → extract a style note (vision) → store it on
    `brand_profile.exemplars`. Capped; extract runs before storage so a vision
    failure persists nothing. Demo-blocked (it mutates the workspace)."""
    existing = (workspace.get("brand_profile") or {}).get("exemplars") or []
    if len(existing) >= MAX_EXEMPLARS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"At most {MAX_EXEMPLARS} example cards per workspace.",
        )
    filename = file.filename or "card"
    media_type = resolve_image_content_type(filename, file.content_type)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file.")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds the {MAX_IMAGE_BYTES // (1024 * 1024)} MB limit.",
        )

    note = await service.propose_exemplar_note(data, media_type)
    workspace_id = str(workspace["_id"])
    exemplar_id = str(ObjectId())
    clean_name = safe_filename(filename)
    storage_key = build_image_key(workspace_id, exemplar_id, clean_name)
    await get_storage().save(storage_key, data)
    exemplar = BrandExemplar(
        id=exemplar_id,
        storage_key=storage_key,
        url=f"/api/workspaces/{workspace_id}/images/file/{exemplar_id}/{clean_name}",
        style_note=note,
    )
    updated = await workspace_service.add_workspace_exemplar(
        db, workspace_id, current_user.id, exemplar
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return updated


@router.delete("/{workspace_id}/exemplars/{exemplar_id}", response_model=WorkspaceResponse)
async def delete_exemplar(
    exemplar_id: str,
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Remove an exemplar and delete its stored bytes."""
    result = await workspace_service.remove_workspace_exemplar(
        db, str(workspace["_id"]), current_user.id, exemplar_id
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    updated, old_key = result
    if old_key:
        await get_storage().delete(old_key)
    return updated
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_exemplars.py -q`
Expected: PASS (all exemplar tests).

- [ ] **Step 5: Commit**

```bash
git add server/app/routes/workspaces.py server/tests/test_exemplars.py
git commit -m "feat(exemplars): POST/DELETE /workspaces/{id}/exemplars routes"
```

---

### Task 7: Inject exemplar guidance into the generate routes

**Files:**
- Modify: `server/app/routes/generate.py`
- Test: `server/tests/test_generate_route.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_generate_route.py`)

```python
def _workspace_with_exemplars() -> dict:
    return {
        "_id": WORKSPACE_OID,
        "owner_id": OWNER_OID,
        "vector_namespace": NS_A,
        "ready_chunk_count": 12,
        "brand_profile": {
            "voice_summary": "Grounded, data-first voice.",
            "exemplars": [{"id": "e1", "storage_key": "k", "url": None,
                           "style_note": "Punchy hook, earthy photography."}],
        },
    }


@pytest.mark.asyncio
async def test_text_generation_injects_exemplar_guidance(client):
    app.dependency_overrides[get_workspace_or_404] = lambda: _workspace_with_exemplars()
    resp = await client.post(
        URL, json={"brief": "hempcrete", "tone": "default", "length": "medium"}
    )
    assert resp.status_code == 200
    system_prompt = client.fake_gen.calls[0][0]  # (system, user) of stream_text
    assert "Punchy hook, earthy photography." in system_prompt
    assert "examples to emulate" in system_prompt.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_generate_route.py::test_text_generation_injects_exemplar_guidance -q`
Expected: FAIL — the exemplar note is not in the system prompt.

- [ ] **Step 3: Edit `server/app/routes/generate.py`**

Add the import:

```python
from app.prompts.exemplars import build_exemplar_guidance
```

In **each** of the three routes (`generate_text`, `generate_card`, `generate_post`), right after the `voice_summary = brand_profile.get("voice_summary")` line, add:

```python
    exemplar_guidance = build_exemplar_guidance(
        [e.get("style_note", "") for e in (brand_profile.get("exemplars") or [])]
    )
```

Then pass it into the system builders:
- In `generate_text`: `system = text_post.build_system(voice_summary, exemplar_guidance)`
- In `generate_card`: `copy_system = image_card.build_copy_system(voice_summary, exemplar_guidance)`
- In `generate_post`: `caption_system = text_post.build_system(voice_summary, exemplar_guidance)`

- [ ] **Step 4: Run the test (and the full generate-route suite) to verify pass**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_generate_route.py -q`
Expected: PASS (all, including the new test).

- [ ] **Step 5: Commit**

```bash
git add server/app/routes/generate.py server/tests/test_generate_route.py
git commit -m "feat(exemplars): inject exemplar guidance into text/card/post prompts"
```

---

### Task 8: Server quality gate

**Files:** none (verification only)

- [ ] **Step 1: ruff + mypy + full pytest**

Run: `cd server && .venv/bin/ruff check app tests && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/mypy app && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest -q`
Expected: ruff clean; mypy clean; all tests pass.

- [ ] **Step 2: Fix any failures, then commit if anything changed**

```bash
git add -A && git commit -m "chore(exemplars): server gate green"
```

(Skip the commit if nothing changed.)

---

### Task 9: Client — types + API mutations

**Files:**
- Modify: `client/src/types/index.ts`
- Modify: `client/src/api/workspaces.ts`

- [ ] **Step 1: Edit `client/src/types/index.ts`**

Add the `BrandExemplar` interface (after `BrandLogo`):

```typescript
export interface BrandExemplar {
  id: string;
  storage_key: string;
  url: string | null;
  style_note: string;
}
```

Add `exemplars` to `BrandProfile`:

```typescript
  exemplars: BrandExemplar[];
```

- [ ] **Step 2: Edit `client/src/api/workspaces.ts`**

Add two mutations after `useExtractBrand`:

```typescript
export function useAddExemplar(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return (await api.post<Workspace>(`/workspaces/${workspaceId}/exemplars`, form)).data;
    },
    onSuccess: (ws) => invalidateWorkspace(qc, ws),
  });
}

export function useRemoveExemplar(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (exemplarId: string) =>
      (await api.delete<Workspace>(`/workspaces/${workspaceId}/exemplars/${exemplarId}`)).data,
    onSuccess: (ws) => invalidateWorkspace(qc, ws),
  });
}
```

- [ ] **Step 3: Typecheck**

Run: `cd client && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add client/src/types/index.ts client/src/api/workspaces.ts
git commit -m "feat(exemplars): client types + add/remove mutations"
```

---

### Task 10: Client — cap helper (pure) + test

**Files:**
- Create: `client/src/features/settings/exemplars.ts`
- Test: `client/src/features/settings/exemplars.test.ts`

- [ ] **Step 1: Write the failing test**

Create `client/src/features/settings/exemplars.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { canAddExemplar, MAX_EXEMPLARS } from "./exemplars";

describe("exemplar cap (Phase 4c)", () => {
  it("allows adding below the cap for a non-demo user", () => {
    expect(canAddExemplar(0, false)).toBe(true);
    expect(canAddExemplar(MAX_EXEMPLARS - 1, false)).toBe(true);
  });
  it("blocks at the cap", () => {
    expect(canAddExemplar(MAX_EXEMPLARS, false)).toBe(false);
  });
  it("blocks for the demo user regardless of count", () => {
    expect(canAddExemplar(0, true)).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/features/settings/exemplars.test.ts`
Expected: FAIL — cannot find module `./exemplars`.

- [ ] **Step 3: Write the implementation**

Create `client/src/features/settings/exemplars.ts`:

```typescript
// Mirrors the server cap (workspace_service.MAX_EXEMPLARS).
export const MAX_EXEMPLARS = 5;

/** Whether the "Add example card" control is enabled. */
export function canAddExemplar(count: number, isDemo: boolean): boolean {
  return !isDemo && count < MAX_EXEMPLARS;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/features/settings/exemplars.test.ts`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add client/src/features/settings/exemplars.ts client/src/features/settings/exemplars.test.ts
git commit -m "feat(exemplars): client cap helper + test"
```

---

### Task 11: Client — ExemplarsSection + wire into Settings

**Files:**
- Create: `client/src/features/settings/ExemplarsSection.tsx`
- Modify: `client/src/features/settings/SettingsPage.tsx`

- [ ] **Step 1: Create `client/src/features/settings/ExemplarsSection.tsx`**

```tsx
import { useEffect, useRef, useState } from "react";
import { ImageOff, Sparkles, Trash2, Upload } from "lucide-react";
import { fetchImageDataUrl } from "@/api/images";
import { useAddExemplar, useRemoveExemplar } from "@/api/workspaces";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/stores/auth";
import type { BrandExemplar, Workspace } from "@/types";
import { canAddExemplar, MAX_EXEMPLARS } from "./exemplars";

/** Settings → Example cards (Phase 4c). Upload past brand cards; each is sent to
 *  Claude vision once, which proposes a short style note stored on the workspace
 *  and injected into generation. Persists immediately (like the logo); disabled
 *  for the demo user and at the cap. */
export function ExemplarsSection({ workspace }: { workspace: Workspace }) {
  const isDemo = useAuthStore((s) => s.user?.is_demo ?? false);
  const add = useAddExemplar(workspace.id);
  const remove = useRemoveExemplar(workspace.id);
  const fileRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const exemplars = workspace.brand_profile.exemplars ?? [];

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setError(null);
    try {
      await add.mutateAsync(file);
    } catch {
      setError("Couldn’t add that card. Use a JPG, PNG, or WebP under 8 MB.");
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-5 shadow-light">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          Example cards · {exemplars.length} of {MAX_EXEMPLARS}
        </span>
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={onFile}
        />
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={() => fileRef.current?.click()}
          loading={add.isPending}
          disabled={!canAddExemplar(exemplars.length, isDemo)}
          title={isDemo ? "Disabled in the demo" : undefined}
        >
          <Upload className="h-4 w-4" aria-hidden />
          Add example card
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        Upload past on-brand cards — each is analyzed once to steer new copy toward your style.
      </p>
      {add.isPending && (
        <span className="flex items-center gap-2 text-xs text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5 animate-pulse" aria-hidden />
          Reading the card…
        </span>
      )}
      {error && <span className="text-xs text-destructive">{error}</span>}
      {exemplars.length === 0 ? (
        <span className="flex items-center gap-2 text-sm text-muted-foreground">
          <ImageOff className="h-4 w-4" aria-hidden />
          No example cards yet.
        </span>
      ) : (
        <ul className="flex flex-col gap-3">
          {exemplars.map((ex) => (
            <ExemplarRow
              key={ex.id}
              exemplar={ex}
              isDemo={isDemo}
              removing={remove.isPending}
              onRemove={() => remove.mutate(ex.id)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function ExemplarRow({
  exemplar,
  isDemo,
  removing,
  onRemove,
}: {
  exemplar: BrandExemplar;
  isDemo: boolean;
  removing: boolean;
  onRemove: () => void;
}) {
  const [dataUrl, setDataUrl] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    if (!exemplar.url) return;
    fetchImageDataUrl(exemplar.url)
      .then((d) => alive && setDataUrl(d))
      .catch(() => alive && setDataUrl(null));
    return () => {
      alive = false;
    };
  }, [exemplar.url]);

  return (
    <li className="flex items-start gap-3 rounded-md border border-border p-2.5">
      <div className="flex h-16 w-[51px] shrink-0 items-center justify-center overflow-hidden rounded bg-surface-variant">
        {dataUrl ? (
          <img src={dataUrl} alt="" className="max-h-full max-w-full object-contain" />
        ) : (
          <span className="h-4 w-4 animate-pulse rounded bg-muted-foreground/30" aria-hidden />
        )}
      </div>
      <p className="flex-1 text-sm leading-relaxed text-foreground">{exemplar.style_note}</p>
      <Button
        type="button"
        size="icon"
        variant="ghost"
        onClick={onRemove}
        loading={removing}
        disabled={isDemo}
        title={isDemo ? "Disabled in the demo" : "Remove"}
        aria-label="Remove example card"
        className="hover:text-destructive"
      >
        <Trash2 className="h-4 w-4" aria-hidden />
      </Button>
    </li>
  );
}
```

- [ ] **Step 2: Wire into `client/src/features/settings/SettingsPage.tsx`**

Add the import:

```typescript
import { ExemplarsSection } from "./ExemplarsSection";
```

Add a section inside the `{workspace && (...)}` brand area — directly after the "Brand identity" `<Section>`:

```tsx
      {workspace && (
        <Section
          title="Example cards"
          hint="Teach the studio your card style by example — uploads steer generated copy."
        >
          <ExemplarsSection workspace={workspace} />
        </Section>
      )}
```

- [ ] **Step 3: Typecheck + lint + format + build**

Run: `cd client && npx tsc --noEmit && npx eslint src && npx prettier --write "src/**/*.{ts,tsx}" && npx vite build`
Expected: tsc clean; eslint clean; prettier writes; build succeeds.

- [ ] **Step 4: Commit**

```bash
git add client/src/features/settings/ExemplarsSection.tsx client/src/features/settings/SettingsPage.tsx
git commit -m "feat(exemplars): Settings Example cards section"
```

---

### Task 12: Full client gate

**Files:** none (verification only)

- [ ] **Step 1: tsc + eslint + prettier + vitest + build**

Run: `cd client && npx tsc --noEmit && npx eslint src && npx prettier --check "src/**/*.{ts,tsx}" && npx vitest run && npx vite build`
Expected: all green.

- [ ] **Step 2: Fix anything; commit if changed**

```bash
git add -A && git commit -m "chore(exemplars): client gate green"
```

(Skip if nothing changed.)

---

### Task 13: Docs

**Files:** `docs/DECISIONS.md`, `docs/phase-4-plan.md`, `CHANGELOG.md`, `docs/DESIGN.md`

- [ ] **Step 1: DECISIONS #23** — in the PR-C clause, change "PR-C (deferred)" to built: note exemplar steering ships — upload past cards → vision `style_note` on `brand_profile.exemplars` (cap 5) → injected as a trusted block into text/card/post system prompts; approximate via archetypes, never pixel-clone; demo-blocked (it persists).

- [ ] **Step 2: `docs/phase-4-plan.md`** — flip the status block and the "PR-C design (deferred)" heading to "built", reflecting the storage shape (`brand_profile.exemplars`), pre-extract-to-text, generate-trio scope.

- [ ] **Step 3: `CHANGELOG.md`** — add a "Phase 4: Brand learning — `0.6.0` *(PR-C: exemplar steering)*" subsection under `[Unreleased]` mirroring the PR-B entry's depth (routes, storage, injection seam, honesty stance, tests: pytest + N total, vitest + N total).

- [ ] **Step 4: `docs/DESIGN.md`** — under the brand-editor bullets, add an "Example cards (Phase 4c)" note: a Settings section with thumbnails + style notes + add/remove, persists immediately, cap 5, demo-disabled.

- [ ] **Step 5: Commit**

```bash
git add docs/DECISIONS.md docs/phase-4-plan.md CHANGELOG.md docs/DESIGN.md
git commit -m "docs(phase-4): PR-C exemplar steering — DECISIONS/PLAN/CHANGELOG/DESIGN"
```

---

### Task 14: Review gate, live verify, PR

**Files:** none (process)

- [ ] **Step 1: Re-run both gates** (server Task 8 + client Task 12 commands) — confirm green.
- [ ] **Step 2: `/code-review`** on the branch diff; fix any real findings.
- [ ] **Step 3: `/security-review`**; fix any real findings. (New surface: Pillow/vision on an untrusted image — already mitigated by the size cap + decompression-bomb guard; ownership + demo guards on the routes.)
- [ ] **Step 4: Live verify (owner, needs the real key):** start server + client, Settings → Example cards → upload 1–2 past cards → confirm a sensible style note → generate a card/post and confirm copy leans toward the exemplars → remove one → confirm the 5-cap and demo-disable.
- [ ] **Step 5: Owner commit/push approval**, then push `feat/4c-exemplars` and open a PR into `dev` (via the GitHub REST API with the keychain token — no `gh` CLI). Update the `bcs-phase-state` memory to mark 4c exemplar steering done when it merges.

---

## Self-Review

**Spec coverage:** pre-extract-to-text (Task 4) ✓; embed on `brand_profile.exemplars` cap 5 (Tasks 3, 5, 6) ✓; generate-trio injection (Tasks 2, 7) ✓; extract-before-store atomicity (Task 6 route) ✓; cap 409 / demo 403 / bad type/size (Task 6 tests) ✓; remove + delete bytes (Task 6) ✓; client section + cap/demo disable (Tasks 9–11) ✓; honesty/no-clone in the prompt (Task 4) ✓; docs (Task 13) ✓; tests pytest + vitest (throughout) ✓.

**Placeholder scan:** none — every code step has full code; doc steps (Task 13) describe concrete edits to specific files mirroring existing entries.

**Type consistency:** `BrandExemplar { id, storage_key, url, style_note }` identical in server model (Task 3), client type (Task 9), route construction (Task 6), and tests; `build_system(voice, exemplar_guidance=None)` / `build_copy_system(...)` signatures match their call sites in Task 7; `propose_exemplar_note(data, media_type)` matches the fake in Task 6 and the route call; `MAX_EXEMPLARS` defined server-side (Task 5) and mirrored client-side (Task 10).
