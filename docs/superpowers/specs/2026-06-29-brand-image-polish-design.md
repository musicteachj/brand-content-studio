# Brand-Image Library Polish — Design

**Goal:** Three incremental improvements to the reusable brand-image library (PR #15): let a one-shot picker upload be **saved to the library** for reuse, **rename** a library image, and **seed demo brand images** so the demo's "Brand images" picker section isn't empty.

**Non-goals (cut, YAGNI at the 24-image cap):** search, tags, reorder, and *auto-capturing* every picker upload (we use an explicit "Save" instead, to keep the library a curated set of *approved* images).

## Background (what exists — PR #15, DECISIONS #28)

- `brand_profile.brand_images[]` = `{ id, storage_key, url, name }`, cap 24. Service: `add_workspace_image` (`$push`) / `remove_workspace_image` (`$pull` + delete bytes). Routes: `POST`/`DELETE /workspaces/{id}/brand-images`. **Demo-blocked.**
- Client: `BrandImagesSection.tsx` (upload + thumbnail grid + delete), `useAddBrandImage`/`useRemoveBrandImage`. The card picker (`ImagePickerPanel`) lists brand images as a third source; its one-shot **Upload** stores bytes via `POST /images/upload` → `onSelectUpload(url, storage_key)` and is **not** added to the library.

## Design

### 1. "Save to brand images" from the picker

In `ImagePickerPanel`, retain the just-uploaded `File` (`onUpload` already has it). When present and the user isn't demo, render a small **"Save to brand images"** button next to the Upload control. It calls the existing `useAddBrandImage(workspaceId).mutateAsync(file)` — **no new route**; the server re-derives the storage key and stores a library copy (a second byte copy of an experiment is acceptable). Shows "Saved ✓" / disables after success; surfaces the cap-409 as a friendly message. Curated-by-choice: only images the user explicitly keeps enter the library.

### 2. Rename a library image

- **Server:** `rename_workspace_image(db, workspace_id, owner_id, image_id, name)` — a targeted update of the matching `brand_images` element's `name` (Mongo `arrayFilters`), clamped to a sane length (e.g. 80 chars). New route `PATCH /workspaces/{id}/brand-images/{image_id}` body `{ name }`, **demo-blocked**, ownership via `get_workspace_or_404`, returns the updated `Workspace`.
- **Client:** `useRenameBrandImage`. In `BrandImagesSection`, each tile gains a small editable name caption (an input saved on blur/Enter); hidden for demo.

### 3. Seed demo brand images (Verdure)

In `seed/seed_demo.py`, generate **2** brand images with Pillow (deterministic, no model calls — same pattern as the seeded logo/exemplars) and `$push` them to `brand_profile.brand_images`. Idempotent (no-op if already present). Makes the demo's picker "Brand images" section non-empty so a visitor can see/select them (selecting is a generation action — demo-allowed).

## Error / edge handling

- Save-to-library at the cap → 409 surfaced as "You've reached the 24-image limit." The picker upload itself still works (the card image is independent of the library).
- Rename: empty name → keep the original filename (no blank labels); over-length → clamped.
- Demo user: save + rename are disabled in the UI and demo-blocked on the server (selecting a seeded brand image still works).
- Deleting a saved library image leaves any card already using it untouched (the card copied its own `CardImage`).

## Testing

- **Server:** `rename_workspace_image` / the PATCH route — renames the right element, clamps length, 404 cross-owner, 403 demo. (`add`/`remove` already covered by `test_brand_images.py`.) Seed test — `seed_demo` adds 2 brand images and is idempotent (extend `test_seed_demo.py`).
- **Client:** `useRenameBrandImage` request shape (mock `api`); the picker "Save to brand images" calls `useAddBrandImage` with the uploaded file (component or hook test).

## Out of scope / later

Search, tags, reorder, auto-capture; bulk operations; cross-workspace image sharing.
