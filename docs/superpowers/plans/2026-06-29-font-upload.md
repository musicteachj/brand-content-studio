# Upload Your Own Brand Fonts (.ttf, full parity) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upload a `.ttf` brand font and have it render with full parity — on the card preview, the Satori PNG export, and embedded in exported PDFs.

**Architecture:** `brand_profile.uploaded_fonts[]` (storage like brand images). Role refs stay name-strings; resolution checks uploaded fonts first. The client font loader becomes source-aware (fetch uploaded bytes auth-gated for Satori `ArrayBuffer` + a data-URL `@font-face`, else the existing fontsource CDN). The PDF renderer registers an uploaded TTF from pre-fetched bytes. No font parsing — the user names the font on upload and we use that name as the family handle everywhere.

**Tech Stack:** FastAPI + Motor + Pillow-free (ReportLab `TTFont`) + pytest (server); React + react-query + Satori + Vitest (client). Server cmds from `server/` (`.venv/bin/...`, model runs prefixed `env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY`); client cmds from `client/` via `./node_modules/.bin/<tool>`.

**Spec:** `docs/superpowers/specs/2026-06-29-font-upload-design.md`

**Branch:** `feat/font-upload` (off `dev`, already created; spec committed).

**File structure:**
- Server: `app/models/common.py` (UploadedFont + field), `app/services/storage_service.py` (`build_font_key`), `app/services/workspace_service.py` (add/remove/resolve), `app/routes/workspaces.py` (3 routes), `app/services/document_service.py` (PDF threading), `app/routes/documents.py` (pre-fetch bytes). Tests: `tests/test_fonts.py` (new), `tests/test_documents.py`.
- Client: `types/index.ts` (UploadedFont + field), `api/workspaces.ts` (useAddFont/useRemoveFont), `styles/brandFonts.ts` (source-aware) + `styles/brandFonts.test.ts` (new), `styles/fontCatalog.ts` (uploaded options), the 5 loader call-sites, new `features/settings/BrandFontsSection.tsx` + `SettingsPage.tsx`.
- Docs: `docs/DECISIONS.md`, `CHANGELOG.md`.

---

### Task 1: Model + service (uploaded fonts)

**Files:**
- Modify: `server/app/models/common.py`, `server/app/services/workspace_service.py`, `server/app/services/storage_service.py`
- Test: `server/tests/test_fonts.py`

- [ ] **Step 1: Write the failing test**

Create `server/tests/test_fonts.py`:

```python
"""Uploaded brand fonts: model + service + (later) routes / PDF embedding."""
import pytest

from app.models.common import BrandProfile, UploadedFont
from app.services.storage_service import build_font_key
from app.services.workspace_service import resolve_uploaded_font


def test_uploaded_font_default_empty():
    assert BrandProfile().uploaded_fonts == []


def test_uploaded_font_shape():
    f = UploadedFont(id="f1", family="Acme Sans", storage_key="k", url="/u")
    assert f.family == "Acme Sans"


def test_build_font_key_is_server_derived():
    assert build_font_key("ws1", "f1", "Acme Sans.ttf") == "ws1/fonts/f1/Acme_Sans.ttf"


def test_resolve_uploaded_font_matches_family():
    bp = {"uploaded_fonts": [{"id": "f1", "family": "Acme Sans", "storage_key": "k1", "url": "/u"}]}
    assert resolve_uploaded_font(bp, "Acme Sans") == "k1"
    assert resolve_uploaded_font(bp, "Inter") is None
    assert resolve_uploaded_font({}, "Acme Sans") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_fonts.py -q`
Expected: FAIL — `UploadedFont` / `build_font_key` / `resolve_uploaded_font` missing.

- [ ] **Step 3: Add the model** to `server/app/models/common.py` — add the class after `BrandImage` and the field to `BrandProfile`:

```python
class UploadedFont(BaseModel):
    """A `.ttf` the owner uploaded; usable as a brand font (`fonts.{heading,body,
    mono}` by family name) with full parity on cards + embedded in PDFs. The
    `family` is the user-given label — also the handle for @font-face / Satori /
    ReportLab (no font parsing)."""

    id: str
    family: str
    storage_key: str
    url: Optional[str] = None
```

In `BrandProfile`, after `brand_images`:

```python
    uploaded_fonts: list[UploadedFont] = Field(default_factory=list)
```

- [ ] **Step 4: Add `build_font_key`** to `server/app/services/storage_service.py` (after `build_image_key`, mirroring it):

```python
def build_font_key(workspace_id: str, font_id: str, filename: str) -> str:
    return f"{workspace_id}/fonts/{font_id}/{safe_filename(filename)}"
```

- [ ] **Step 5: Add service fns** to `server/app/services/workspace_service.py`. Extend the `common` import to include `UploadedFont`, then add (after `rename_workspace_image`):

```python
def resolve_uploaded_font(brand_profile: dict, family: Optional[str]) -> Optional[str]:
    """Storage key of an uploaded font matching `family`, or None."""
    if not family:
        return None
    for f in (brand_profile or {}).get("uploaded_fonts") or []:
        if f.get("family") == family:
            return f.get("storage_key")
    return None


async def add_workspace_font(
    db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str, font: UploadedFont
) -> Optional[WorkspaceResponse]:
    """Append an uploaded font to `brand_profile.uploaded_fonts` (targeted $push)."""
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    if not doc:
        return None
    now = utcnow()
    await db.workspaces.update_one(
        {"_id": doc["_id"]},
        {"$push": {"brand_profile.uploaded_fonts": font.model_dump()},
         "$set": {"updated_at": now}},
    )
    bp = doc.setdefault("brand_profile", {})
    bp.setdefault("uploaded_fonts", []).append(font.model_dump())
    doc["updated_at"] = now
    return _to_response(doc)


async def remove_workspace_font(
    db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str, font_id: str
) -> Optional[tuple[WorkspaceResponse, Optional[str]]]:
    """Pull an uploaded font by id; return the updated workspace + its storage key."""
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    if not doc:
        return None
    fonts = (doc.get("brand_profile") or {}).get("uploaded_fonts") or []
    old_key = next((f.get("storage_key") for f in fonts if f.get("id") == font_id), None)
    now = utcnow()
    await db.workspaces.update_one(
        {"_id": doc["_id"]},
        {"$pull": {"brand_profile.uploaded_fonts": {"id": font_id}}, "$set": {"updated_at": now}},
    )
    bp = doc.setdefault("brand_profile", {})
    bp["uploaded_fonts"] = [f for f in fonts if f.get("id") != font_id]
    doc["updated_at"] = now
    return _to_response(doc), old_key
```

- [ ] **Step 6: Run to verify it passes**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_fonts.py -q`
Expected: PASS (4 passed).

- [ ] **Step 7: Commit**

```bash
git add server/app/models/common.py server/app/services/storage_service.py server/app/services/workspace_service.py server/tests/test_fonts.py
git commit -m "feat(fonts): uploaded-font model + service + storage key"
```

---

### Task 2: Upload / delete / serve routes

**Files:**
- Modify: `server/app/routes/workspaces.py`
- Test: `server/tests/test_fonts.py`

- [ ] **Step 1: Add the failing tests** to `server/tests/test_fonts.py`. Append a route-test block (mirrors `test_brand_images.py`'s harness):

```python
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
from app.main import app
from app.models.common import utcnow
from app.models.user import UserInDB
from app.services.storage_service import get_storage
from app.utils.dependencies import get_current_user
from tests.conftest import TEST_DB_NAME

WS = ObjectId()
OWNER = ObjectId()
TTF_HEX = "0001000000010000"  # sfnt version 1.0 header (enough for the route's checks)


def _user(is_demo=False, owner=OWNER):
    return UserInDB(id=str(owner), email="o@e.com", hashed_password="x", full_name="O",
                    is_demo=is_demo)


async def _seed(db, fonts=None):
    await db.workspaces.insert_one({
        "_id": WS, "owner_id": OWNER, "name": "V", "slug": "v",
        "brand_profile": {"uploaded_fonts": fonts or []}, "vector_namespace": str(WS),
        "embedding_model": settings.embedding_model, "embedding_dim": settings.embedding_dim,
        "asset_count": 0, "ready_chunk_count": 0, "created_at": utcnow(), "updated_at": utcnow(),
    })


async def _mk(test_db, tmp_path, monkeypatch, *, is_demo=False, owner=OWNER, fonts=None):
    monkeypatch.setattr(settings, "database_name", TEST_DB_NAME)
    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    get_storage.cache_clear()
    await _seed(test_db, fonts)
    app.dependency_overrides[get_database] = lambda: test_db
    app.dependency_overrides[get_current_user] = lambda: _user(is_demo, owner)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _url():
    return f"/api/workspaces/{WS}/fonts"


@pytest_asyncio.fixture
async def fc(test_db, tmp_path, monkeypatch):
    ac = await _mk(test_db, tmp_path, monkeypatch)
    async with ac:
        yield ac
    app.dependency_overrides.clear()
    get_storage.cache_clear()


@pytest.mark.asyncio
async def test_add_font_stores_and_appends(fc):
    resp = await fc.post(_url(), data={"name": "Acme Sans"},
                         files={"file": ("acme.ttf", bytes.fromhex(TTF_HEX), "font/ttf")})
    assert resp.status_code == 200
    fonts = resp.json()["brand_profile"]["uploaded_fonts"]
    assert fonts[0]["family"] == "Acme Sans"
    assert fonts[0]["storage_key"].startswith(f"{WS}/fonts/")
    assert await get_storage().read(fonts[0]["storage_key"]) == bytes.fromhex(TTF_HEX)


@pytest.mark.asyncio
async def test_add_font_rejects_non_ttf(fc):
    resp = await fc.post(_url(), data={"name": "X"},
                         files={"file": ("x.otf", b"hi", "font/otf")})
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_add_font_demo_blocked(test_db, tmp_path, monkeypatch):
    ac = await _mk(test_db, tmp_path, monkeypatch, is_demo=True)
    async with ac:
        resp = await ac.post(_url(), data={"name": "X"},
                             files={"file": ("x.ttf", bytes.fromhex(TTF_HEX), "font/ttf")})
    app.dependency_overrides.clear()
    get_storage.cache_clear()
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_and_serve_font(fc):
    add = await fc.post(_url(), data={"name": "Acme"},
                        files={"file": ("acme.ttf", bytes.fromhex(TTF_HEX), "font/ttf")})
    font = add.json()["brand_profile"]["uploaded_fonts"][0]
    fid = font["id"]
    served = await fc.get(font["url"])
    assert served.status_code == 200
    assert served.content == bytes.fromhex(TTF_HEX)
    resp = await fc.delete(f"{_url()}/{fid}")
    assert resp.status_code == 200
    assert resp.json()["brand_profile"]["uploaded_fonts"] == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_fonts.py -k "add_font or delete_and_serve" -q`
Expected: FAIL — routes 404/405.

- [ ] **Step 3: Add the routes** to `server/app/routes/workspaces.py`. Extend imports — `Form`, `Response`, `build_font_key`, `UploadedFont`:

```python
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
```
```python
from app.models.common import BrandExemplar, BrandImage, BrandLogo, UploadedFont
```
```python
from app.services.storage_service import build_font_key, build_image_key, get_storage, safe_filename
```

Add constants near `MAX_BRAND_IMAGES` import usage (top of module, after `router = APIRouter()`):

```python
MAX_UPLOADED_FONTS = 8
MAX_FONT_BYTES = 5 * 1024 * 1024  # 5 MB
```

Add the routes after `rename_brand_image`:

```python
@router.post("/{workspace_id}/fonts", response_model=WorkspaceResponse)
async def add_font(
    name: str = Form(...),
    file: UploadFile = ...,
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Upload a `.ttf` brand font (name = the family handle). Demo-blocked, capped."""
    existing = (workspace.get("brand_profile") or {}).get("uploaded_fonts") or []
    if len(existing) >= MAX_UPLOADED_FONTS:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"At most {MAX_UPLOADED_FONTS} fonts per workspace.")
    family = name.strip()[:80]
    if not family:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A font name is required.")
    if any(f.get("family") == family for f in existing):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A font with that name exists.")
    filename = file.filename or "font.ttf"
    if not filename.lower().endswith(".ttf"):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail="Unsupported font. Upload a .ttf file.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file.")
    if len(data) > MAX_FONT_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"Font exceeds the {MAX_FONT_BYTES // (1024 * 1024)} MB limit.")
    workspace_id = str(workspace["_id"])
    font_id = str(ObjectId())
    clean_name = safe_filename(filename)
    key = build_font_key(workspace_id, font_id, clean_name)
    await get_storage().save(key, data)
    font = UploadedFont(
        id=font_id, family=family, storage_key=key,
        url=f"/api/workspaces/{workspace_id}/fonts/file/{font_id}/{clean_name}",
    )
    updated = await workspace_service.add_workspace_font(db, workspace_id, current_user.id, font)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return updated


@router.delete("/{workspace_id}/fonts/{font_id}", response_model=WorkspaceResponse)
async def delete_font(
    font_id: str,
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Remove an uploaded font and delete its stored bytes. A card/PDF already
    rendered is unaffected; a role still naming it falls back to serif/Georgia."""
    result = await workspace_service.remove_workspace_font(
        db, str(workspace["_id"]), current_user.id, font_id
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    updated, old_key = result
    if old_key:
        await get_storage().delete(old_key)
    return updated


@router.get("/{workspace_id}/fonts/file/{font_id}/{filename}")
async def serve_font(
    font_id: str,
    filename: str,
    workspace: dict = Depends(get_workspace_or_404),
):
    """Serve an uploaded font's bytes. Ownership via the dependency; the key is
    rebuilt server-side (storage's traversal guard rejects anything escaping root)."""
    key = build_font_key(str(workspace["_id"]), font_id, filename)
    try:
        data = await get_storage().read(key)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Font not found")
    return Response(content=data, media_type="font/ttf")
```

(Note: `Form`/`Response`/`build_image_key` may already be imported — keep one copy; `build_image_key` stays for the existing image routes.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_fonts.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/app/routes/workspaces.py server/tests/test_fonts.py
git commit -m "feat(fonts): demo-guarded upload/delete + auth-gated serve routes"
```

---

### Task 3: PDF embedding of uploaded fonts

**Files:**
- Modify: `server/app/services/document_service.py`, `server/app/routes/documents.py`
- Test: `server/tests/test_fonts.py`

- [ ] **Step 1: Write the failing test** — append to `server/tests/test_fonts.py` (uses a real bundled TTF's bytes as a stand-in uploaded font):

```python
def test_register_pdf_font_uses_uploaded_bytes():
    from pathlib import Path

    from app.services import document_service as ds

    ttf = (Path(ds.__file__).resolve().parents[1] / "assets" / "fonts" / "inter.ttf").read_bytes()
    ds._REGISTERED.clear()
    name = ds._register_pdf_font("Acme Sans", "body", {"Acme Sans": ttf})
    assert name == "bcs-body-acme-sans"  # embedded, not a base-14 fallback
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_fonts.py -k register_pdf -q`
Expected: FAIL — `_register_pdf_font` takes 2 args.

- [ ] **Step 3: Thread uploaded bytes through the PDF path** in `server/app/services/document_service.py`.

Change `_register_pdf_font` to accept an uploaded-bytes map and prefer it:

```python
def _register_pdf_font(
    family: str | None, role: str, uploaded: dict[str, bytes] | None = None
) -> str:
    """Return a ReportLab font name: an uploaded TTF (by family) or an embedded
    brand TTF when available, else a base-14 serif/sans fallback (bold for headings)."""
    src: str | io.BytesIO | None = None
    if uploaded and family and family in uploaded:
        src = io.BytesIO(uploaded[family])
    elif resolve_font_file(family):
        src = resolve_font_file(family)
    if src is not None:
        name = f"bcs-{role}-{font_slug(family or '')}"
        if name in _REGISTERED:
            return name
        try:
            pdfmetrics.registerFont(TTFont(name, src))
            _REGISTERED.add(name)
            return name
        except Exception:  # noqa: BLE001 — a bad font file must not break rendering
            pass
    if role == "heading":
        return "Times-Bold" if is_serif(family) else "Helvetica-Bold"
    return "Times-Roman" if is_serif(family) else "Helvetica"
```

Add `import io` at the top of the file if not present.

Thread `uploaded` through `render_pdf` and `build_document_files`. Change their signatures and the call:

```python
def render_pdf(document: dict, brand_profile: dict, uploaded_fonts: dict[str, bytes] | None = None) -> bytes:
```
(inside `render_pdf`, pass `uploaded_fonts` to each `_register_pdf_font(...)` call — there are heading/body calls; add the 3rd arg `uploaded_fonts`.)

```python
def build_document_files(
    document: dict, brand_profile: dict, uploaded_fonts: dict[str, bytes] | None = None
) -> dict[str, bytes]:
    return {
        "docx": render_docx(document, brand_profile),
        "pdf": render_pdf(document, brand_profile, uploaded_fonts),
        "pptx": render_pptx(document, brand_profile),
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_fonts.py -k register_pdf -q`
Expected: PASS.

- [ ] **Step 5: Pre-fetch uploaded font bytes in the route** — `server/app/routes/documents.py`. Before the `build_document_files` call (line ~105), gather the bytes for the selected heading/body families that are uploaded:

```python
            bp = brand_profile
            up_fonts = (bp.get("fonts") or {})
            wanted = {up_fonts.get("heading"), up_fonts.get("body")}
            uploaded_font_bytes: dict[str, bytes] = {}
            for f in (bp.get("uploaded_fonts") or []):
                if f.get("family") in wanted and f.get("storage_key"):
                    try:
                        uploaded_font_bytes[f["family"]] = await get_storage().read(f["storage_key"])
                    except (FileNotFoundError, ValueError):
                        pass
            files = document_service.build_document_files(
                output["document"], brand_profile, uploaded_font_bytes
            )
```

(Replace the existing single `files = document_service.build_document_files(output["document"], brand_profile)` line with the block above. `get_storage` is already imported in this route.)

- [ ] **Step 6: Run the document tests**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_documents.py tests/test_fonts.py -q`
Expected: PASS (existing document tests still green; the 2-arg `build_document_files`/`render_pdf` calls default `uploaded_fonts=None`).

- [ ] **Step 7: Commit**

```bash
git add server/app/services/document_service.py server/app/routes/documents.py server/tests/test_fonts.py
git commit -m "feat(fonts): embed uploaded TTF in exported PDFs (parity)"
```

---

### Task 4: Server gate

- [ ] **Step 1: ruff + mypy + full pytest**

Run: `cd server && .venv/bin/ruff check app tests seed && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/mypy app && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest -q`
Expected: clean; all pass.

- [ ] **Step 2: Fix anything; commit if changed**

```bash
git add -A && git commit -m "chore(fonts): server gate green"
```

---

### Task 5: Client types + API hooks

**Files:**
- Modify: `client/src/types/index.ts`, `client/src/api/workspaces.ts`

- [ ] **Step 1: Add the type** in `client/src/types/index.ts` — `UploadedFont` (near `BrandImage`) and the field on `BrandProfile`:

```ts
export interface UploadedFont {
  id: string;
  family: string;
  storage_key: string;
  url: string | null;
}
```
Add to `BrandProfile` (after `brand_images`):
```ts
  uploaded_fonts: UploadedFont[];
```

- [ ] **Step 2: Add hooks** to `client/src/api/workspaces.ts` (after `useRenameBrandImage`):

```ts
export function useAddFont(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { file: File; name: string }) => {
      const form = new FormData();
      form.append("file", input.file);
      form.append("name", input.name);
      return (await api.post<Workspace>(`/workspaces/${workspaceId}/fonts`, form)).data;
    },
    onSuccess: (ws) => invalidateWorkspace(qc, ws),
  });
}

export function useRemoveFont(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (fontId: string) =>
      (await api.delete<Workspace>(`/workspaces/${workspaceId}/fonts/${fontId}`)).data,
    onSuccess: (ws) => invalidateWorkspace(qc, ws),
  });
}
```

- [ ] **Step 3: Typecheck**

Run: `cd client && ./node_modules/.bin/tsc --noEmit`
Expected: errors where `BrandProfile` literals lack `uploaded_fonts` (fix those fixtures — add `uploaded_fonts: []` — if tsc flags any; the useActiveWorkspace test's `ws()` builder is the likely one).

- [ ] **Step 4: Commit**

```bash
git add client/src/types/index.ts client/src/api/workspaces.ts
git commit -m "feat(fonts): client UploadedFont type + add/remove hooks"
```

---

### Task 6: Source-aware font loader

**Files:**
- Modify: `client/src/styles/brandFonts.ts`
- Test: `client/src/styles/brandFonts.test.ts`

- [ ] **Step 1: Write the failing test**

Create `client/src/styles/brandFonts.test.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { loadBrandFontBuffers } from "./brandFonts";
import type { BrandFonts, UploadedFont } from "@/types";

const FONTS: BrandFonts = { heading: "Acme Sans", body: "Acme Sans", mono: null };

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({
      ok: true,
      arrayBuffer: async () => new Uint8Array([url.startsWith("/") ? 1 : 2]).buffer,
    })),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("loadBrandFontBuffers source-awareness", () => {
  it("fetches uploaded fonts from their own (same-origin) url", async () => {
    const uploaded: UploadedFont[] = [
      { id: "f1", family: "Acme Sans", storage_key: "k", url: "/api/workspaces/w/fonts/file/f1/a.ttf" },
    ];
    const out = await loadBrandFontBuffers(FONTS, uploaded);
    expect(out.length).toBeGreaterThan(0);
    expect(out.every((f) => f.name === "Acme Sans")).toBe(true);
    const calledOwnUrl = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.some(
      ([u]) => typeof u === "string" && u.includes("/fonts/file/"),
    );
    expect(calledOwnUrl).toBe(true);
  });

  it("falls back to the CDN when the family isn't uploaded", async () => {
    await loadBrandFontBuffers(FONTS, []);
    const calledCdn = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.some(
      ([u]) => typeof u === "string" && u.includes("cdn.jsdelivr.net"),
    );
    expect(calledCdn).toBe(true);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd client && ./node_modules/.bin/vitest run src/styles/brandFonts.test.ts`
Expected: FAIL — `loadBrandFontBuffers` takes one arg / no uploaded path.

- [ ] **Step 3: Make the loader source-aware** in `client/src/styles/brandFonts.ts`.

(a) Add imports + helpers near the top (after the existing imports):

```ts
import { useAuthStore } from "@/stores/auth";
import type { BrandFonts, UploadedFont } from "@/types";

function uploadedUrl(family: string, uploaded: UploadedFont[]): string | null {
  return uploaded.find((f) => f.family === family)?.url ?? null;
}

async function fetchFontBytes(url: string): Promise<ArrayBuffer | null> {
  const cached = bufferCache.get(url);
  if (cached) return cached;
  const sameOrigin = url.startsWith("/") && !url.startsWith("//");
  const token = useAuthStore.getState().token;
  try {
    const resp = await fetch(url, {
      headers: sameOrigin && token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!resp.ok) return null;
    const buf = await resp.arrayBuffer();
    bufferCache.set(url, buf);
    return buf;
  } catch {
    return null;
  }
}

function bufferToDataUrl(buf: ArrayBuffer): string {
  let binary = "";
  const bytes = new Uint8Array(buf);
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return `data:font/ttf;base64,${btoa(binary)}`;
}
```

(Remove the now-duplicate `import type { BrandFonts } ...` if one already exists — keep a single import that includes `UploadedFont`.)

(b) Replace `loadBrandFontBuffers`:

```ts
export async function loadBrandFontBuffers(
  fonts: BrandFonts,
  uploaded: UploadedFont[] = [],
): Promise<SatoriFont[]> {
  const out = await Promise.all(
    requiredFonts(fonts).map(async (req) => {
      const up = uploadedUrl(req.family, uploaded);
      const data = up ? await fetchFontBytes(up) : await loadBuffer(req.family, req.weight);
      return data
        ? ({ name: req.family, data, weight: req.weight, style: "normal" } as SatoriFont)
        : null;
    }),
  );
  return out.filter((f): f is SatoriFont => f !== null);
}
```

(c) Refactor the `@font-face` injection to share a helper and accept uploaded fonts. Replace `injectBrandFontFaces` and `injectFontFace` with:

```ts
function appendFontFace(family: string, weight: number, src: string): void {
  const style = document.createElement("style");
  style.dataset.brandFont = `${family}:${weight}`;
  style.textContent = `@font-face{font-family:"${family}";font-style:normal;font-weight:${weight};font-display:swap;src:url("${src}") format("truetype");}`;
  document.head.appendChild(style);
}

function injectFamily(family: string, weight: number, uploaded: UploadedFont[]): void {
  const key = `${family}:${weight}`;
  if (injected.has(key)) return;
  injected.add(key);
  const up = uploadedUrl(family, uploaded);
  if (up) {
    void fetchFontBytes(up).then((buf) => {
      if (buf) appendFontFace(family, weight, bufferToDataUrl(buf));
      else injected.delete(key);
    });
  } else {
    appendFontFace(family, weight, ttfUrl(family, weight));
  }
}

export function injectBrandFontFaces(fonts: BrandFonts, uploaded: UploadedFont[] = []): void {
  if (typeof document === "undefined") return;
  for (const req of requiredFonts(fonts)) injectFamily(req.family, req.weight, uploaded);
}

export function injectFontFace(family: string, uploaded: UploadedFont[] = []): void {
  if (typeof document === "undefined" || !family.trim()) return;
  injectFamily(family, 400, uploaded);
}
```

(This preserves behavior for the CDN path and adds the uploaded path; `injected`/`bufferCache`/`ttfUrl`/`requiredFonts`/`loadBuffer` already exist.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd client && ./node_modules/.bin/vitest run src/styles/brandFonts.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add client/src/styles/brandFonts.ts client/src/styles/brandFonts.test.ts
git commit -m "feat(fonts): source-aware loader (uploaded bytes vs CDN)"
```

---

### Task 7: Picker options + thread uploaded fonts into callers

**Files:**
- Modify: `client/src/styles/fontCatalog.ts` (+ its test), the 5 loader call-sites.

- [ ] **Step 1: Extend `optionsForRole`** in `client/src/styles/fontCatalog.ts` to append uploaded families. Add a parameter + a test.

Add to `fontCatalog.test.ts`:

```ts
it("appends uploaded font families to every role", () => {
  const opts = optionsForRole("heading", null, ["Acme Sans"]);
  expect(opts.map((o) => o.value)).toContain("Acme Sans");
  expect(optionsForRole("mono", null, ["Acme Sans"]).map((o) => o.value)).toContain("Acme Sans");
});
```

Then change `optionsForRole`:

```ts
export function optionsForRole(
  role: FontRole,
  current: string | null,
  uploaded: string[] = [],
): FontSelectOption[] {
  const cats: FontCategory[] = role === "mono" ? ["mono"] : ["serif", "sans"];
  const families = FONT_OPTIONS.filter((o) => cats.includes(o.category)).map((o) => o.family);
  const opts: FontSelectOption[] = [
    { value: "", label: "Default" },
    ...families.map((f) => ({ value: f, label: f })),
    ...uploaded.map((f) => ({ value: f, label: `${f} (uploaded)` })),
  ];
  if (current && !families.includes(current) && !uploaded.includes(current)) {
    opts.push({ value: current, label: `${current} (current)` });
  }
  return opts;
}
```

- [ ] **Step 2: Thread `uploaded_fonts` into the loader call-sites.** Each call passes the workspace's uploaded fonts (degrade to `[]` where the brand snapshot lacks them):

  - `client/src/features/generate/useCardExport.ts:42` → `await loadBrandFontBuffers(props.brand.fonts, props.brand.uploaded_fonts ?? []);`
  - `client/src/features/generate/CardPreview.tsx:129` → `injectBrandFontFaces(brand.fonts, brand.uploaded_fonts ?? []);`
  - `client/src/features/generate/DeckPreview.tsx:49` → `injectBrandFontFaces(brand.fonts, brand.uploaded_fonts ?? []);`
  - `client/src/features/generate/DocumentPage.tsx:26` → `injectBrandFontFaces(brand.fonts, brand.uploaded_fonts ?? []);`
  - `client/src/features/settings/BrandIdentityEditor.tsx:542` → `if (family) injectFontFace(family, workspace.brand_profile.uploaded_fonts ?? []);` (the `FontPreview` here receives `family`; pass the uploaded fonts via a new prop `uploaded` from the editor, which has `workspace`. Add `uploaded={workspace.brand_profile.uploaded_fonts}` to each `<FontPreview .../>` and a `uploaded: UploadedFont[]` prop on `FontPreview`, then `injectFontFace(family, uploaded)`.)

  Also use the uploaded families in the editor's selects: where `optionsForRole("heading", watch("fonts.heading"))` is called (3 sites), add the uploaded families list: `optionsForRole("heading", watch("fonts.heading"), workspace.brand_profile.uploaded_fonts.map((f) => f.family))`.

  (`HistoryPage.tsx:124` and `CardThumb.tsx` keep the default `[]` — thumbnails fall back for uploaded fonts, acceptable.)

- [ ] **Step 3: Typecheck + lint + format**

Run: `cd client && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/eslint src && ./node_modules/.bin/prettier --write "src/**/*.{ts,tsx}"`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add client/src/styles/fontCatalog.ts client/src/styles/fontCatalog.test.ts client/src/features/generate/useCardExport.ts client/src/features/generate/CardPreview.tsx client/src/features/generate/DeckPreview.tsx client/src/features/generate/DocumentPage.tsx client/src/features/settings/BrandIdentityEditor.tsx
git commit -m "feat(fonts): picker lists uploaded families + thread into card/preview/export"
```

---

### Task 8: Settings "Brand fonts" section

**Files:**
- Create: `client/src/features/settings/BrandFontsSection.tsx`
- Modify: `client/src/features/settings/SettingsPage.tsx`

- [ ] **Step 1: Create `client/src/features/settings/BrandFontsSection.tsx`** (mirrors `BrandImagesSection`: upload [file + name] / list / delete; demo-aware):

```tsx
import { useRef, useState } from "react";
import { Trash2, Type, Upload } from "lucide-react";
import { useAddFont, useRemoveFont } from "@/api/workspaces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuthStore } from "@/stores/auth";
import type { Workspace } from "@/types";

const MAX_FONTS = 8;

/** Settings → Brand fonts. Upload your own .ttf fonts; they appear in the font
 *  picker and render on cards + embed in PDFs. Demo-blocked; capped. */
export function BrandFontsSection({ workspace }: { workspace: Workspace }) {
  const isDemo = useAuthStore((s) => s.user?.is_demo ?? false);
  const add = useAddFont(workspace.id);
  const remove = useRemoveFont(workspace.id);
  const fileRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const fonts = workspace.brand_profile.uploaded_fonts ?? [];

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!name.trim()) {
      setError("Give the font a name first (e.g. its family name).");
      return;
    }
    setError(null);
    try {
      await add.mutateAsync({ file, name: name.trim() });
      setName("");
    } catch {
      setError("Couldn’t add that font. Upload a .ttf under 5 MB with a unique name.");
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-5 shadow-light">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          Brand fonts · {fonts.length} of {MAX_FONTS}
        </span>
        <div className="flex items-center gap-2">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Font name (e.g. Acme Sans)"
            className="h-8 w-44 text-sm"
            disabled={isDemo}
          />
          <input ref={fileRef} type="file" accept=".ttf" className="hidden" onChange={onFile} />
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={() => fileRef.current?.click()}
            loading={add.isPending}
            disabled={isDemo || fonts.length >= MAX_FONTS}
            title={isDemo ? "Disabled in the demo" : undefined}
          >
            <Upload className="h-4 w-4" aria-hidden />
            Add .ttf
          </Button>
        </div>
      </div>
      <p className="text-sm text-muted-foreground">
        Upload your own TrueType fonts — they appear in the font picker and render on cards and in
        exported PDFs.
      </p>
      {error && <span className="text-xs text-destructive">{error}</span>}
      {fonts.length === 0 ? (
        <span className="flex items-center gap-2 text-sm text-muted-foreground">
          <Type className="h-4 w-4" aria-hidden />
          No uploaded fonts yet.
        </span>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {fonts.map((f) => (
            <li key={f.id} className="flex items-center justify-between rounded-md border border-border px-3 py-2">
              <span className="text-sm text-foreground" style={{ fontFamily: `"${f.family}", serif` }}>
                {f.family}
              </span>
              {!isDemo && (
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  onClick={() => remove.mutate(f.id)}
                  loading={remove.isPending}
                  aria-label={`Remove ${f.family}`}
                  className="h-7 w-7 hover:text-destructive"
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Mount it** in `client/src/features/settings/SettingsPage.tsx` — import and add a Section after the Brand images section:

```tsx
import { BrandFontsSection } from "./BrandFontsSection";
```
```tsx
      {workspace && (
        <Section
          title="Brand fonts"
          hint="Upload your own .ttf fonts to use across cards and documents."
        >
          <BrandFontsSection workspace={workspace} />
        </Section>
      )}
```

- [ ] **Step 3: Typecheck + lint + format**

Run: `cd client && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/eslint src && ./node_modules/.bin/prettier --write "src/**/*.{ts,tsx}"`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add client/src/features/settings/BrandFontsSection.tsx client/src/features/settings/SettingsPage.tsx
git commit -m "feat(fonts): Settings 'Brand fonts' upload/manage section"
```

---

### Task 9: Client gate

- [ ] **Step 1: tsc + eslint + prettier + vitest + build**

Run: `cd client && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/eslint src && ./node_modules/.bin/prettier --check "src/**/*.{ts,tsx}" && ./node_modules/.bin/vitest run && ./node_modules/.bin/vite build`
Expected: all green (vitest +~3).

- [ ] **Step 2: Fix anything; commit if changed**

```bash
git add -A && git commit -m "chore(fonts): client gate green"
```

---

### Task 10: Docs

**Files:** `docs/DECISIONS.md`, `CHANGELOG.md`

- [ ] **Step 1: DECISIONS** — add a row after the `#31` row:

```
| 32 | Upload your own brand fonts (.ttf, full parity) | Owners can upload a `.ttf` (+ a name) to `brand_profile.uploaded_fonts[]` (cap 8) and use it as a brand font with **full parity** — card preview, Satori PNG export, **and** embedded in exported PDFs. Role refs stay name-strings; resolution checks uploaded fonts first. **No font parsing** — the user-given name is the family handle for `@font-face` / Satori / ReportLab alike. The client font loader becomes **source-aware** (fetch uploaded bytes auth-gated → Satori `ArrayBuffer` + a data-URL `@font-face`, else the existing fontsource CDN); the PDF renderer registers an uploaded TTF from pre-fetched bytes (`io.BytesIO` → ReportLab `TTFont`). Demo-blocked; auth-gated serve route; nothing leaks the file's internal name. **Deferred:** `.otf`/`.woff2` (need a `fontTools` CFF→TTF step), multi-weight uploads. | curated fonts only covered Google Fonts; a brand's own typeface had no path | Reuses the brand-image storage pattern + the existing font pipeline; assigning the family name avoids a `fontTools` dependency; checking uploaded-first keeps catalog/CDN fonts unchanged. |
```

- [ ] **Step 2: CHANGELOG** — under `## [Unreleased]`, add at the top:

```markdown
### Added — Upload your own brand fonts

Upload a `.ttf` (with a name) in **Settings → Brand fonts** and use it as a brand font with full parity: it renders on the card preview, the PNG export, **and** embeds in exported PDFs. Stored on `brand_profile.uploaded_fonts[]` (cap 8, demo-blocked, auth-gated serving). The client font loader is now source-aware (uploaded bytes fetched auth-gated for Satori + a data-URL `@font-face`, else the fontsource CDN), and the PDF renderer registers an uploaded TTF via ReportLab. No font parsing — the name you give the font is its handle everywhere. `.otf`/`.woff2` and multi-weight uploads are noted as fast-follows. See [`docs/DECISIONS.md`](./docs/DECISIONS.md) (#32). Tests: pytest (+N) — model/service/routes/PDF embed; vitest (+N) — source-aware loader + picker options.
```

(Fill the `+N` counts from the actual gate output.)

- [ ] **Step 3: Commit**

```bash
git add docs/DECISIONS.md CHANGELOG.md
git commit -m "docs(fonts): upload your own brand fonts — DECISIONS #32 + CHANGELOG"
```

---

### Task 11: Review, verify, PR

- [ ] **Step 1: Re-run both gates** (Task 4 + Task 9) — confirm green.
- [ ] **Step 2: `/code-review`** the branch diff; fix real findings.
- [ ] **Step 3: `/security-review`**; fix real findings. (Surface: font upload is `.ttf`-only + size-capped + demo-guarded; the serve route rebuilds the key server-side [traversal-safe] and is ownership-scoped; uploaded bytes are parsed by ReportLab inside a `try/except` so a malformed font can't break rendering; the auth-gated client fetch sends the bearer only same-origin.)
- [ ] **Step 4: Live verify (owner):** Settings → **Brand fonts** → upload a `.ttf` with a name → it appears in the Heading/Body font dropdowns (Brand identity) → select it → Save → a generated **card renders in it** (preview + exported PNG) → generate a **document and export the PDF** → the body is the uploaded font (embedded), not a generic serif. Delete it → roles fall back cleanly.
- [ ] **Step 5: Owner commit/push approval**, then push `feat/font-upload` and open a PR into `dev` (REST API + keychain token; no `gh`).

---

## Self-Review

**Spec coverage:** `uploaded_fonts[]` model + cap (Task 1) ✓; storage + upload/delete/serve routes, `.ttf`/5 MB/cap/demo/dedupe (Task 2) ✓; PDF embedding via pre-fetched bytes (Task 3) ✓; client type + hooks (Task 5) ✓; source-aware loader — Satori buffers + data-URL `@font-face`, uploaded-first (Task 6) ✓; picker lists uploaded families + threaded into card/preview/export/editor (Task 7) ✓; Settings management section (Task 8) ✓; name-on-upload / no parsing (Tasks 2,6 — family is the assigned handle) ✓; `.otf`/`.woff2`/multi-weight deferred (docs) ✓; tests server + client (throughout) ✓; docs (Task 10) ✓.

**Placeholder scan:** none except the doc `+N` test counts (Task 10), explicitly to be filled from gate output.

**Type consistency:** `UploadedFont {id,family,storage_key,url}` (server Task 1 / client Task 5) matches everywhere. `resolve_uploaded_font(brand_profile, family)` (Task 1) — server only. `_register_pdf_font(family, role, uploaded)` + `render_pdf(...,uploaded_fonts)` + `build_document_files(...,uploaded_fonts)` (Task 3) are consistent and default to `None` so existing 2-arg callers/tests still pass. Client `loadBrandFontBuffers(fonts, uploaded=[])`, `injectBrandFontFaces(fonts, uploaded=[])`, `injectFontFace(family, uploaded=[])` (Task 6) match the call-site edits (Task 7) and the `optionsForRole(role, current, uploaded=[])` signature (Task 7). `useAddFont({file,name})` / `useRemoveFont(fontId)` (Task 5) match `BrandFontsSection` (Task 8).
```
