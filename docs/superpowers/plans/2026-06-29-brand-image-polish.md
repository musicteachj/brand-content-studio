# Brand-Image Library Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Save a one-shot picker upload into the brand-image library, rename a library image, and seed demo brand images.

**Architecture:** Incremental on PR #15. Save-to-library reuses the existing `useAddBrandImage` via a new `onSaveBrandImage` picker callback (no new route). Rename adds a targeted `PATCH …/brand-images/{id}` + service fn + an editable caption. Seed adds a Pillow generator + an idempotent `_ensure_brand_images` to `seed_demo`.

**Tech Stack:** FastAPI + Motor + Pydantic + Pillow + pytest (server); React + react-query + Vitest (client). Server cmds from `server/` (`.venv/bin/...`, model-touching runs prefixed `env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY`); client cmds from `client/` via `./node_modules/.bin/<tool>`.

**Spec:** `docs/superpowers/specs/2026-06-29-brand-image-polish-design.md`

**Branch:** `feat/brand-image-polish` (off `dev`, already created; spec committed).

**File structure:**
- Modify `server/app/models/workspace.py` — `BrandImageRename` body model.
- Modify `server/app/services/workspace_service.py` — `rename_workspace_image`.
- Modify `server/app/routes/workspaces.py` — `PATCH …/brand-images/{image_id}`.
- Modify `server/tests/test_brand_images.py` — rename route tests.
- Modify `server/seed/seed_demo.py` — `_generate_brand_image` + `_ensure_brand_images` + call.
- Modify `server/tests/test_seed_demo.py` — generator test.
- Modify `client/src/api/workspaces.ts` — `useRenameBrandImage`.
- Modify `client/src/features/generate/ImagePickerPanel.tsx` (+ `.test.tsx`) — "Save to brand images".
- Modify `client/src/features/generate/GeneratePage.tsx` — wire `onSaveBrandImage`.
- Modify `client/src/features/settings/BrandImagesSection.tsx` — editable name caption.
- Docs: `docs/DECISIONS.md`, `CHANGELOG.md`.

---

### Task 1: Rename a brand image (server)

**Files:**
- Modify: `server/app/models/workspace.py`, `server/app/services/workspace_service.py`, `server/app/routes/workspaces.py`
- Test: `server/tests/test_brand_images.py`

- [ ] **Step 1: Write the failing tests** — in `server/tests/test_brand_images.py`, after `test_delete_brand_image_pulls_and_removes_bytes`, add:

```python
async def _seed_one_image(test_db, monkeypatch, *, is_demo=False, owner=OWNER_OID):
    img = {"id": "img1", "storage_key": "k1", "url": "/u", "name": "old.png"}
    return await _mk(test_db, __import__("pathlib").Path("/tmp"), monkeypatch, is_demo=is_demo,
                     owner=owner, brand_images=[img])


@pytest.mark.asyncio
async def test_rename_brand_image_updates_name(test_db, tmp_path, monkeypatch):
    img = {"id": "img1", "storage_key": "k1", "url": "/u", "name": "old.png"}
    ac = await _mk(test_db, tmp_path, monkeypatch, brand_images=[img])
    async with ac:
        resp = await ac.patch(f"{_url()}/img1", json={"name": "Forest texture"})
    app.dependency_overrides.clear()
    get_storage.cache_clear()
    assert resp.status_code == 200
    names = [i["name"] for i in resp.json()["brand_profile"]["brand_images"]]
    assert names == ["Forest texture"]


@pytest.mark.asyncio
async def test_rename_brand_image_blank_keeps_existing(test_db, tmp_path, monkeypatch):
    img = {"id": "img1", "storage_key": "k1", "url": "/u", "name": "old.png"}
    ac = await _mk(test_db, tmp_path, monkeypatch, brand_images=[img])
    async with ac:
        resp = await ac.patch(f"{_url()}/img1", json={"name": "   "})
    app.dependency_overrides.clear()
    get_storage.cache_clear()
    assert resp.json()["brand_profile"]["brand_images"][0]["name"] == "old.png"


@pytest.mark.asyncio
async def test_rename_brand_image_clamps_length(test_db, tmp_path, monkeypatch):
    img = {"id": "img1", "storage_key": "k1", "url": "/u", "name": "old.png"}
    ac = await _mk(test_db, tmp_path, monkeypatch, brand_images=[img])
    async with ac:
        resp = await ac.patch(f"{_url()}/img1", json={"name": "x" * 200})
    app.dependency_overrides.clear()
    get_storage.cache_clear()
    assert len(resp.json()["brand_profile"]["brand_images"][0]["name"]) == 80


@pytest.mark.asyncio
async def test_rename_brand_image_demo_blocked(test_db, tmp_path, monkeypatch):
    img = {"id": "img1", "storage_key": "k1", "url": "/u", "name": "old.png"}
    ac = await _mk(test_db, tmp_path, monkeypatch, is_demo=True, brand_images=[img])
    async with ac:
        resp = await ac.patch(f"{_url()}/img1", json={"name": "X"})
    app.dependency_overrides.clear()
    get_storage.cache_clear()
    assert resp.status_code == 403
```

(Remove the unused `_seed_one_image` helper if you prefer — it's optional; the tests above don't use it. Drop it to keep ruff happy.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_brand_images.py -k rename -q`
Expected: FAIL — the PATCH route 405s (not defined).

- [ ] **Step 3: Add the body model** to `server/app/models/workspace.py` (after `WorkspaceUpdate`):

```python
class BrandImageRename(BaseModel):
    name: str = Field(default="", max_length=500)  # clamped to 80 in the service
```

- [ ] **Step 4: Add `rename_workspace_image`** to `server/app/services/workspace_service.py` (after `remove_workspace_image`):

```python
async def rename_workspace_image(
    db: AsyncIOMotorDatabase, workspace_id: str, owner_id: str, image_id: str, name: str
) -> Optional[WorkspaceResponse]:
    """Set a brand image's display name (targeted arrayFilters update). A blank
    name is ignored (keeps the existing label); long names clamp to 80."""
    doc = await _get_owned_doc(db, workspace_id, owner_id)
    if not doc:
        return None
    clean = name.strip()[:80]
    now = utcnow()
    if clean:
        await db.workspaces.update_one(
            {"_id": doc["_id"]},
            {"$set": {"brand_profile.brand_images.$[img].name": clean, "updated_at": now}},
            array_filters=[{"img.id": image_id}],
        )
        for img in (doc.get("brand_profile") or {}).get("brand_images") or []:
            if img.get("id") == image_id:
                img["name"] = clean
    doc["updated_at"] = now
    return _to_response(doc)
```

- [ ] **Step 5: Add the route** to `server/app/routes/workspaces.py`. Extend the `app.models.workspace` import to include `BrandImageRename`:

```python
from app.models.workspace import (
    BrandExtractResponse,
    BrandImageRename,
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceUpdate,
)
```

Add the route after `delete_brand_image`:

```python
@router.patch("/{workspace_id}/brand-images/{image_id}", response_model=WorkspaceResponse)
async def rename_brand_image(
    image_id: str,
    payload: BrandImageRename,
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Rename a brand image's display label. Demo-blocked (it mutates)."""
    updated = await workspace_service.rename_workspace_image(
        db, str(workspace["_id"]), current_user.id, image_id, payload.name
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return updated
```

- [ ] **Step 6: Run to verify it passes**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_brand_images.py -k rename -q`
Expected: PASS (4 passed).

- [ ] **Step 7: Commit**

```bash
git add server/app/models/workspace.py server/app/services/workspace_service.py server/app/routes/workspaces.py server/tests/test_brand_images.py
git commit -m "feat(brand-images): demo-guarded rename route + service"
```

---

### Task 2: Seed demo brand images

**Files:**
- Modify: `server/seed/seed_demo.py`
- Test: `server/tests/test_seed_demo.py`

- [ ] **Step 1: Write the failing test** — in `server/tests/test_seed_demo.py`, extend the `from seed.seed_demo import (...)` block to include `_generate_brand_image`, and add:

```python
def test_seed_brand_image_is_valid_png():
    img = Image.open(BytesIO(_generate_brand_image("Forest texture")))
    assert img.format == "PNG"
    assert img.size == (1080, 1350)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_seed_demo.py -k brand_image -q`
Expected: FAIL — `_generate_brand_image` not defined (ImportError).

- [ ] **Step 3: Add the generator** to `server/seed/seed_demo.py` (after `_generate_card`):

```python
def _generate_brand_image(label: str) -> bytes:
    """A deterministic branded swatch for the demo brand-image library."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1080, 1350), _FOREST)
    d = ImageDraw.Draw(img)
    d.rectangle([60, 60, 1020, 1290], outline=_OCHRE, width=8)
    d.text((90, 1190), label.upper(), font=_font(44), fill=_CREAM)
    return _png_bytes(img)
```

- [ ] **Step 4: Add `_ensure_brand_images`** to `server/seed/seed_demo.py` (after `_ensure_exemplars`):

```python
async def _ensure_brand_images(db, workspace: dict) -> None:
    fresh = await db.workspaces.find_one({"_id": workspace["_id"]})
    if (fresh.get("brand_profile") or {}).get("brand_images"):
        print("✓ brand images exist")
        return
    ws_id = str(workspace["_id"])
    images = []
    for label in ("Forest texture", "Ochre accent"):
        img_id = str(ObjectId())
        name = f"{label.lower().replace(' ', '-')}.png"
        key = build_image_key(ws_id, img_id, name)
        await get_storage().save(key, _generate_brand_image(label))
        images.append(
            {
                "id": img_id,
                "storage_key": key,
                "url": f"/api/workspaces/{ws_id}/images/file/{img_id}/{name}",
                "name": name,
            }
        )
    await db.workspaces.update_one(
        {"_id": workspace["_id"]},
        {"$set": {"brand_profile.brand_images": images, "updated_at": datetime.now(timezone.utc)}},
    )
    print(f"+ seeded {len(images)} brand images")
```

- [ ] **Step 5: Call it** in `server/seed/seed_demo.py` `main()`, after `await _ensure_exemplars(db, workspace)`:

```python
    await _ensure_brand_images(db, workspace)
```

- [ ] **Step 6: Run to verify it passes**

Run: `cd server && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest tests/test_seed_demo.py -k brand_image -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add server/seed/seed_demo.py server/tests/test_seed_demo.py
git commit -m "feat(brand-images): seed 2 demo brand images for Verdure"
```

---

### Task 3: Server gate

- [ ] **Step 1: ruff + mypy + full pytest**

Run: `cd server && .venv/bin/ruff check app tests seed && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/mypy app && env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest -q`
Expected: ruff clean; mypy clean; all pass (≈133).

- [ ] **Step 2: Fix anything; commit if changed**

```bash
git add -A && git commit -m "chore(brand-images): server gate green"
```

---

### Task 4: "Save to brand images" in the picker

**Files:**
- Modify: `client/src/features/generate/ImagePickerPanel.tsx`
- Test: `client/src/features/generate/ImagePickerPanel.test.tsx`

- [ ] **Step 1: Add the failing test** — in `client/src/features/generate/ImagePickerPanel.test.tsx`, the `@/api/images` mock's `uploadImage` must resolve an upload result, and add a test. Update the hoisted mock so `uploadImage` resolves:

```ts
const { uploadImage, useUnsplashSearch, fetchImageDataUrl } = vi.hoisted(() => ({
  uploadImage: vi.fn(() => Promise.resolve({ url: "/u", storage_key: "k1", source: "upload" })),
  useUnsplashSearch: vi.fn(() => ({ data: undefined, isLoading: false, isError: false })),
  fetchImageDataUrl: vi.fn(() => Promise.resolve("data:image/png;base64,AAAA")),
}));
```

Add the test (uses the existing `mount`, which already passes `open`/`workspaceId`/handlers):

```tsx
it("offers Save to brand images after an upload and passes the file", async () => {
  const onSaveBrandImage = vi.fn(() => Promise.resolve());
  mount({ onSaveBrandImage });
  const file = new File(["x"], "shot.png", { type: "image/png" });
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  Object.defineProperty(input, "files", { value: [file] });
  await act(async () => {
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
  const save = document.querySelector('[aria-label="Save to brand images"]') as HTMLElement;
  expect(save).not.toBeNull();
  await act(async () => {
    save.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  expect(onSaveBrandImage).toHaveBeenCalledWith(file);
});
```

(The `mount` helper already spreads `props`, so `onSaveBrandImage` flows through; `act` is already imported in this file.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd client && ./node_modules/.bin/vitest run src/features/generate/ImagePickerPanel.test.tsx`
Expected: FAIL — no Save control / prop.

- [ ] **Step 3: Add the prop + button** in `client/src/features/generate/ImagePickerPanel.tsx`.

Add to `Props` (after `onSelectUpload`):

```tsx
  onSaveBrandImage?: (file: File) => Promise<void>;
```

Destructure it in the component signature (add `onSaveBrandImage,`). Add state (near the other `useState`s):

```tsx
  const [lastUpload, setLastUpload] = useState<File | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
```

In `onUpload`, after `onSelectUpload(res.url, res.storage_key);`, record the file:

```tsx
      onSelectUpload(res.url, res.storage_key);
      setLastUpload(file);
      setSaved(false);
```

Add the save handler (below `onUpload`):

```tsx
  async function saveToBrandImages() {
    if (!onSaveBrandImage || !lastUpload) return;
    setSaving(true);
    setUploadError(null);
    try {
      await onSaveBrandImage(lastUpload);
      setSaved(true);
    } catch {
      setUploadError("Couldn’t save to brand images (the 24-image limit may be reached).");
    } finally {
      setSaving(false);
    }
  }
```

Render the button right after the `Upload` button's hidden `<input>` (inside the same row, after the file `<input ... onChange={onUpload} />`):

```tsx
              {onSaveBrandImage && lastUpload && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={saveToBrandImages}
                  loading={saving}
                  disabled={saved}
                  aria-label="Save to brand images"
                >
                  {saved ? "Saved ✓" : "Save to brand images"}
                </Button>
              )}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd client && ./node_modules/.bin/vitest run src/features/generate/ImagePickerPanel.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add client/src/features/generate/ImagePickerPanel.tsx client/src/features/generate/ImagePickerPanel.test.tsx
git commit -m "feat(brand-images): 'Save to brand images' in the card picker"
```

---

### Task 5: Wire the picker + rename hook + rename UI

**Files:**
- Modify: `client/src/api/workspaces.ts`, `client/src/features/generate/GeneratePage.tsx`, `client/src/features/settings/BrandImagesSection.tsx`

- [ ] **Step 1: Add `useRenameBrandImage`** to `client/src/api/workspaces.ts` (after `useRemoveBrandImage`):

```ts
export function useRenameBrandImage(workspaceId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { imageId: string; name: string }) =>
      (
        await api.patch<Workspace>(
          `/workspaces/${workspaceId}/brand-images/${input.imageId}`,
          { name: input.name },
        )
      ).data,
    onSuccess: (ws) => invalidateWorkspace(qc, ws),
  });
}
```

- [ ] **Step 2: Wire `onSaveBrandImage` into both pickers** in `client/src/features/generate/GeneratePage.tsx`. In each of `PostPackMode` and `CardMode`, add (next to the existing `useActiveWorkspace`/hooks):

```tsx
  const isDemo = useAuthStore((s) => s.user?.is_demo ?? false);
  const addBrandImage = useAddBrandImage(workspaceId);
```

Add the imports at the top of the file:

```tsx
import { useAddBrandImage } from "@/api/workspaces";
import { useAuthStore } from "@/stores/auth";
```

Then add the prop to **both** `ImagePickerPanel` usages (after `brandImages={...}`):

```tsx
        onSaveBrandImage={
          isDemo ? undefined : (file) => addBrandImage.mutateAsync(file).then(() => undefined)
        }
```

- [ ] **Step 3: Add the editable name caption** in `client/src/features/settings/BrandImagesSection.tsx`. Extend the section to pass a rename handler, and the tile to render an editable caption.

In `BrandImagesSection`, add the hook + pass `onRename` to each tile:

```tsx
  const rename = useRenameBrandImage(workspace.id);
```

(extend the `@/api/workspaces` import to include `useRenameBrandImage`.)

Pass to `ImageTile`:

```tsx
              onRename={(name) => rename.mutate({ imageId: img.id, name })}
```

Update `ImageTile`'s prop type + body. Add `onRename: (name: string) => void;` to its props, and replace the returned `<li>` with a flex column that adds a caption input below the image:

```tsx
  return (
    <li className="flex flex-col gap-1">
      <div className="group relative aspect-square overflow-hidden rounded-md border border-border bg-surface-variant">
        {dataUrl ? (
          <img src={dataUrl} alt={image.name ?? ""} className="h-full w-full object-cover" />
        ) : (
          <span className="absolute inset-0 animate-pulse bg-muted-foreground/10" aria-hidden />
        )}
        {!isDemo && (
          <Button
            type="button"
            size="icon"
            variant="secondary"
            onClick={onRemove}
            loading={removing}
            aria-label={`Remove ${image.name ?? "image"}`}
            className="absolute right-1 top-1 h-7 w-7 opacity-0 shadow-medium transition-opacity focus-visible:opacity-100 group-hover:opacity-100 hover:text-destructive"
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden />
          </Button>
        )}
      </div>
      {isDemo ? (
        <span className="truncate text-[11px] text-muted-foreground">{image.name}</span>
      ) : (
        <input
          defaultValue={image.name ?? ""}
          aria-label="Rename image"
          onBlur={(e) => {
            const v = e.target.value.trim();
            if (v && v !== image.name) onRename(v);
          }}
          onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
          className="w-full rounded-sm border border-transparent bg-transparent px-1 text-[11px] text-muted-foreground hover:border-border focus:border-border focus:outline-none"
        />
      )}
    </li>
  );
```

- [ ] **Step 4: Typecheck + lint + format**

Run: `cd client && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/eslint src && ./node_modules/.bin/prettier --write "src/**/*.{ts,tsx}"`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add client/src/api/workspaces.ts client/src/features/generate/GeneratePage.tsx client/src/features/settings/BrandImagesSection.tsx
git commit -m "feat(brand-images): wire Save-to-library + rename caption"
```

---

### Task 6: Client gate

- [ ] **Step 1: tsc + eslint + prettier + vitest + build**

Run: `cd client && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/eslint src && ./node_modules/.bin/prettier --check "src/**/*.{ts,tsx}" && ./node_modules/.bin/vitest run && ./node_modules/.bin/vite build`
Expected: all green (vitest +1).

- [ ] **Step 2: Fix anything; commit if changed**

```bash
git add -A && git commit -m "chore(brand-images): client gate green"
```

---

### Task 7: Docs

**Files:** `docs/DECISIONS.md`, `CHANGELOG.md`

- [ ] **Step 1: DECISIONS** — add a row after the `#30` row:

```
| 31 | Brand-image library polish | Three incremental adds to the library (#28): (1) **Save to brand images** from the card picker — a one-shot upload can be kept for reuse via the existing `useAddBrandImage` (a new `onSaveBrandImage` picker callback, no new route); explicit, not auto-capture, so the library stays a *curated* set. (2) **Rename** — a demo-blocked `PATCH …/brand-images/{id}` (targeted arrayFilters `$set`; blank kept, clamped to 80) + an editable caption per tile. (3) **Seed 2 demo brand images** (Pillow, idempotent) so the demo picker section isn't empty. **Cut (YAGNI at the 24 cap):** search, tags, reorder, auto-capture. | the library could only be filled from Settings, images had only their original filename, and the demo's picker section was empty | Each piece reuses the existing library machinery (add hook / targeted update / seed pattern); the explicit Save keeps "approved images" curated; cap-24 makes search/tags/reorder unnecessary. |
```

- [ ] **Step 2: CHANGELOG** — under `## [Unreleased]`, add at the top:

```markdown
### Added — Brand-image library polish

Three small improvements to the reusable brand-image library: **Save to brand images** from the card image picker (keep a one-shot upload for reuse — explicit, so the library stays curated), **rename** a library image (an editable caption + demo-blocked `PATCH …/brand-images/{id}`), and **2 seeded demo brand images** so the demo's picker section isn't empty. Search/tags/reorder stayed cut (unnecessary at the 24-image cap). See [`docs/DECISIONS.md`](./docs/DECISIONS.md) (#31). Tests: pytest (+5) — rename (update/blank/clamp/demo) + the seed generator; vitest (+1) — the picker Save control.
```

- [ ] **Step 3: Commit**

```bash
git add docs/DECISIONS.md CHANGELOG.md
git commit -m "docs(brand-images): polish — DECISIONS #31 + CHANGELOG"
```

---

### Task 8: Review, verify, PR

- [ ] **Step 1: Re-run both gates** (Task 3 + Task 6) — confirm green.
- [ ] **Step 2: `/code-review`** the branch diff; fix real findings.
- [ ] **Step 3: `/security-review`**; fix real findings. (Surface: rename is ownership + demo guarded and only mutates a string label via arrayFilters; save-to-library re-uploads the user's own file through the existing demo-guarded route — no new storage/path surface.)
- [ ] **Step 4: Live verify (owner):** card picker → Upload an image → **Save to brand images** → it appears in Settings → Brand images and in the picker's Brand-images source on the next card; **rename** a library image (edit the caption, blur) → the label sticks; re-seed (`npm run seed`) or sign in as demo → the demo picker shows the 2 seeded brand images.
- [ ] **Step 5: Owner commit/push approval**, then push `feat/brand-image-polish` and open a PR into `dev` (REST API + keychain token; no `gh`).

---

## Self-Review

**Spec coverage:** save-to-library via `onSaveBrandImage` reusing `useAddBrandImage`, explicit button (Tasks 4–5) ✓; rename service+route+model, blank-keeps/clamp-80/demo-blocked (Task 1) + editable caption (Task 5) ✓; seed 2 demo brand images idempotent + generator test (Task 2) ✓; cut search/tags/reorder/auto-capture (not built) ✓; demo behavior — save/rename demo-blocked, seeded images selectable (Tasks 1,5 + seed) ✓; tests server + client (throughout) ✓; docs (Task 7) ✓.

**Placeholder scan:** none — every code step is concrete. (The optional `_seed_one_image` helper in Task 1 Step 1 is explicitly marked removable.)

**Type consistency:** `rename_workspace_image(db, ws_id, owner, image_id, name)` (Task 1) matches the route call. `BrandImageRename.name` (Task 1) matches the route body + the client PATCH `{name}` (Task 5). `onSaveBrandImage?: (file) => Promise<void>` (Task 4) matches the GeneratePage wiring `addBrandImage.mutateAsync(file).then(() => undefined)` (Task 5) and the test (Task 4). `useRenameBrandImage({imageId, name})` (Task 5) matches its `ImageTile.onRename` use. `_generate_brand_image(label)` (Task 2) matches the test + `_ensure_brand_images` call.
```
