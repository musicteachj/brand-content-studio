# Reusable Brand-Image Library — Design

**Goal:** Let an owner upload images **once** into a per-workspace library and reuse them as the card picture on any number of cards — closing the gap next to Unsplash ("I have my own photos I want to re-use"). Today the picker's "Upload" is one-shot: the image persists only onto that one generation's `output.image`.

## Scope decisions

- **Embed on the workspace** — `brand_profile.brand_images[]`, mirroring `exemplars`/`logo` (no new collection, no new serve route).
- **Explicit curation in Settings + a third source in the picker.** Saving = approving (no approval workflow).
- **Separate from exemplars** — exemplars steer the *model* via style notes; brand images are the actual card *picture*. Different jobs; shared storage pattern only.
- Deleting a library image does **not** touch images already baked onto past cards (those are copied onto the generation). Mutations are **demo-blocked** (like logo/exemplars). Cap **24** per workspace.

## Architecture

A brand image is just a stored image that, once chosen, becomes a normal `source:"upload"` `CardImage`. So this is near-total reuse of the exemplar/logo machinery **minus the vision step** — no change to how images attach to or render/export on cards.

### Server (FastAPI)

- **Model** (`app/models/common.py`): `BrandImage { id, storage_key, url, name }` (`name` = original filename, for a picker label). Add `brand_images: list[BrandImage] = Field(default_factory=list)` to `BrandProfile`.
- **Service** (`app/services/workspace_service.py`): `add_workspace_image`, `remove_workspace_image` — copies of `add_workspace_exemplar`/`remove_workspace_exemplar` targeting `brand_profile.brand_images` (`$push` / `$pull` by `id`; delete returns the old storage key).
- **Routes** (`app/routes/workspaces.py`): `MAX_BRAND_IMAGES = 24`; `POST /{workspace_id}/brand-images` (validate → `get_storage().save` → push; cap → 409) and `DELETE /{workspace_id}/brand-images/{image_id}` (pull → delete bytes). Both `Depends(require_not_demo)` + `get_workspace_or_404`. **No vision call** (unlike exemplars). Reuse already-imported `resolve_image_content_type`, `MAX_IMAGE_BYTES`, `build_image_key`, `safe_filename`, `get_storage`. The existing serve route (`/workspaces/{id}/images/file/{image_id}/{filename}`) already serves these bytes.

### Client (React)

- **Types** (`types/index.ts`): `BrandImage` + `brand_images: BrandImage[]` on `BrandProfile`.
- **API hooks** (`api/workspaces.ts`): `useAddBrandImage`, `useRemoveBrandImage` — copies of `useAddExemplar`/`useRemoveExemplar` at `/brand-images`.
- **Settings** — new `features/settings/BrandImagesSection.tsx` (mirror `ExemplarsSection.tsx`: upload + thumbnail grid + delete, demo-aware), mounted in `SettingsPage.tsx`.
- **Picker third source** (`features/generate/ImagePickerPanel.tsx`): a new `brandImages: BrandImage[]` prop renders a "Brand images" section of selectable tiles. Selecting calls the existing `onSelectUpload(image.url, image.storage_key)` — a brand image is an `upload`-sourced `CardImage`, so `selectUpload` (auth-gated fetch → data URL → persist on generation) handles it unchanged; `selectedKey` already matches on `storage_key`.
- **Wire** (`features/generate/GeneratePage.tsx`, both picker usages): `brandImages={workspace?.brand_profile.brand_images ?? []}`.

## Error / edge handling

- Empty/oversized/wrong-type upload → the existing image validators (400 / 413 / 415).
- Over cap → 409 with a clear message.
- Demo user → 403 on add/delete; Settings UI disables them (demo notice).
- A brand image deleted from the library still renders on past cards (its bytes + `CardImage` were copied onto the generation). The library tile just disappears from the picker.
- Cross-owner → 404 via `get_workspace_or_404`.

## Testing

- **Server** `tests/test_brand_images.py`: add → present on `brand_profile.brand_images`; delete → pulled (+ bytes deleted); cap → 409; demo → 403; cross-owner → 404.
- **Client** `ImagePickerPanel.test.tsx`: renders brand-image tiles; selecting one calls `onSelectUpload(url, storage_key)`. (Optional `BrandImagesSection` render/delete test.)

## Out of scope (v1)

Seeding demo brand images for Verdure; tags/folders/search/rename/reorder; auto-capturing one-shot picker uploads into the library (the library is explicit-upload only).
