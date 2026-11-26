# Reusable Brand-Image Library

## Context

Users can already put **their own** images on cards: the card image picker
(`client/src/features/generate/ImagePickerPanel.tsx`) offers Unsplash search **and**
an ad-hoc "Upload" button (`POST /workspaces/{id}/images/upload`). But that upload is
**one-shot** — the image is persisted only onto that single generation's `output.image`,
with **no way to reuse it on a later card**. To reuse an image today, the user must
re-upload it every time.

This adds a **reusable, per-workspace "brand images" library**: upload images once (in
Settings, alongside Logo / Example cards), then pick any of them when choosing a card
image. It closes the natural gap next to Unsplash — "I have my own photos I want to use
and re-use."

**Scope decisions (confirmed):** embed the library on the workspace
(`brand_profile.brand_images[]`, mirroring `exemplars`/`logo`); explicit curation in
Settings **plus** a third source in the picker; kept **separate** from exemplars
(exemplars steer the *model* via style notes — brand images are the actual card
*picture*). No approval workflow (saving = approving); deleting from the library does
**not** touch images already baked onto past cards (those are copied onto the
generation); all mutations **demo-blocked** like logo/exemplars.

## Approach

A brand image is just a stored image the user can later select; once chosen it becomes a
normal `source:"upload"` `CardImage` on the generation. So this is **near-total reuse of
the existing exemplar/logo machinery, minus the vision step** — no new collection, no new
serve route, no change to how images attach to or render on cards.

### Server (FastAPI)

- **Model** — `server/app/models/common.py`: add `BrandImage` (mirror `BrandExemplar`
  without `style_note`): `{ id, storage_key, url, name }` (`name` = original filename for
  a picker label). Add `brand_images: list[BrandImage] = Field(default_factory=list)` to
  `BrandProfile`.
- **Service** — `server/app/services/workspace_service.py`: add `add_workspace_image` and
  `remove_workspace_image`, copied from `add_workspace_exemplar` / `remove_workspace_exemplar`
  (lines 140–176) with `brand_profile.brand_images` as the target (`$push` / `$pull` by
  `id`, returning the updated workspace + old storage key on delete).
- **Routes** — `server/app/routes/workspaces.py`: add `MAX_BRAND_IMAGES = 24` near
  `MAX_EXEMPLARS`, then `POST /{workspace_id}/brand-images` and
  `DELETE /{workspace_id}/brand-images/{image_id}`, modeled on the exemplar routes
  (150–214). **Difference from exemplars:** no `BrandExtractService` / vision call — just
  validate → `get_storage().save(...)` → push. Reuse the already-imported
  `resolve_image_content_type`, `MAX_IMAGE_BYTES`, `build_image_key`, `safe_filename`,
  `get_storage`. Cap → 409; both routes `Depends(require_not_demo)`; ownership via
  `get_workspace_or_404`. The **existing** serve route
  (`GET /workspaces/{id}/images/file/{image_id}/{filename}` in `routes/images.py`) already
  serves anything stored via `build_image_key` — no change.

### Client (React)

- **Types** — `client/src/types/index.ts`: add `BrandImage` interface and
  `brand_images: BrandImage[]` on `BrandProfile` (next to `exemplars`).
- **API hooks** — `client/src/api/workspaces.ts`: add `useAddBrandImage` /
  `useRemoveBrandImage`, copied from `useAddExemplar` / `useRemoveExemplar` (109–127),
  pointing at `/brand-images`.
- **Settings management** — new `client/src/features/settings/BrandImagesSection.tsx`
  (mirror `ExemplarsSection.tsx`: upload control + grid of thumbnails with a delete
  button, demo-aware via the existing `DemoNotice` pattern). Mount it in
  `SettingsPage.tsx` next to the exemplars section.
- **Picker third source** — `ImagePickerPanel.tsx`: accept a new `brandImages: BrandImage[]`
  prop and render a "Brand images" section of selectable tiles above/below the Unsplash
  grid. Selecting one calls the **existing** `onSelectUpload(image.url, image.storage_key)`
  — a brand image is an `upload`-sourced `CardImage`, so the current `selectUpload` flow
  (auth-gated fetch → data URL → persist on generation, in `useCardGeneration.ts` /
  `usePostPackGeneration.ts`) handles it unchanged. `selectedKey` already matches on
  `storage_key`, so the selected check mark works for free.
- **Wire the prop** — `GeneratePage.tsx` (both `ImagePickerPanel` usages, ~lines 180/379):
  pass `brandImages={workspace?.brand_profile.brand_images ?? []}` (it already has
  `workspace` from `useActiveWorkspace`).

### Docs

`docs/DECISIONS.md` (#28 — the brand-image library, embedded-on-workspace + picker-source
+ separate-from-exemplars rationale), `CHANGELOG.md` under `[Unreleased]`.

## Critical files

- Server: `models/common.py`, `services/workspace_service.py`, `routes/workspaces.py`,
  new `tests/test_brand_images.py`.
- Client: `types/index.ts`, `api/workspaces.ts`, new `features/settings/BrandImagesSection.tsx`,
  `features/settings/SettingsPage.tsx`, `features/generate/ImagePickerPanel.tsx`,
  `features/generate/GeneratePage.tsx`, new `features/generate/ImagePickerPanel.test.tsx`.

## Reuse (don't re-implement)

- Exemplar route/service pattern (`routes/workspaces.py:150–214`,
  `workspace_service.py:140–176`) — brand images are the same minus the vision step.
- Logo's targeted `brand_profile.*` `$set`/`$push` updates (`workspace_service.py:102–137`).
- `build_image_key` / `safe_filename` / `get_storage` / the existing image serve route.
- Client: `ExemplarsSection.tsx` + `useAddExemplar`/`useRemoveExemplar`; the picker's
  existing `onSelectUpload` → `selectUpload` path (no change to card render/export).

## Testing / verification

- **Server** (`cd server`, `env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY .venv/bin/python -m pytest -q`):
  new `tests/test_brand_images.py` — add returns the image on `brand_profile.brand_images`;
  delete pulls it (and the route deletes the bytes); cap → 409; demo user → 403;
  cross-owner → 404. Plus `ruff` + `mypy`.
- **Client** (`cd client`, `./node_modules/.bin/vitest run`): `ImagePickerPanel.test.tsx`
  — renders the brand-images tiles and selecting one calls `onSelectUpload(url, storage_key)`;
  (optional) a `BrandImagesSection` render/delete test. Plus `tsc` + `eslint` + `prettier`
  + `vite build`.
- **Manual:** Settings → Brand images → upload two images; Generate a card → open the image
  picker → "Brand images" → pick one → it renders on the card and exports in the PNG;
  delete one in Settings and confirm a previously-exported/History card is unaffected.
  As the demo user, the Settings upload is blocked (403) and disabled in the UI.

## Out of scope (v1)

- Seeding demo brand images for Verdure (so the demo picker section is non-empty) — nice
  follow-up, not required.
- Tags/folders/search within the library; per-image rename; drag-reorder.
- Surfacing uploaded card images (the one-shot path) into the library automatically — the
  library is explicit-upload only.

## Process

On approval: branch `feat/brand-image-library` off `dev`, follow the usual loop — write the
in-repo spec + plan under `docs/superpowers/` (house style), TDD per task, server + client
gates, `/code-review` + `/security-review`, owner live-test, then PR into `dev`.
