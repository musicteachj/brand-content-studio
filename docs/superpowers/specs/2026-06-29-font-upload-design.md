# Upload Your Own Brand Fonts — Design

**Goal:** Let an owner upload a `.ttf` font and use it as a brand font with **full parity** — it renders identically on the live card preview, the Satori PNG export, **and** embedded in exported `.docx`/PDF documents — for brands whose typeface isn't on Google Fonts.

**Non-goals (v1):** `.otf` / `.woff2` (need a `fontTools`/`brotli` CFF→TTF conversion step — neither installed; deferred); true multi-weight uploads (one file = one weight); auto-extracting the font's internal family name (the user provides a name; see below).

## Background (current font system)

- `brand_profile.fonts = { heading, body, mono }` are **family-name strings**. A **curated `<Select>`** (`client/src/styles/fontCatalog.ts`) drives them (DECISIONS #29).
- **Cards:** `client/src/styles/brandFonts.ts` turns a family name into a font by building a **fontsource CDN URL** (`ttfUrl(family, weight)`): `loadBrandFontBuffers` (Satori `ArrayBuffer`s) + `injectBrandFontFaces`/`injectFontFace` (DOM `@font-face`). Both are **CDN-by-name** — they have no concept of a font we host.
- **PDF:** `document_service._register_pdf_font(family, role)` → `brand_fonts.resolve_font_file(family)` → a bundled `{slug}.ttf` in `brand_fonts_dir`, registered with ReportLab `TTFont`; else a serif/sans base font.
- Storage pattern (logo / brand images / exemplars): `storage_service` bytes + a metadata entry on `brand_profile`, demo-guarded routes, an auth-gated serve route. `fontTools`/`brotli` are **not** installed.

**Key simplification — no font parsing.** `@font-face`'s family, Satori's `name`, and ReportLab's registered name are all **names we assign**. So the user gives the font a **label on upload**, and we use that label as the family handle everywhere; the glyphs come from the bytes regardless of the file's internal name. No `fontTools` dependency.

## Design

### Data model

`brand_profile.uploaded_fonts: list[UploadedFont]` where `UploadedFont = { id, family, storage_key, url }`. Cap **8**. The role refs (`fonts.{heading,body,mono}`) stay **name strings, unchanged** — resolution checks `uploaded_fonts` **first** (workspace-specific wins), else the curated catalog (CDN) / bundled TTF. One file = one weight, used for all weights (Satori falls back to nearest; ReportLab reuses it — the same single-weight behavior bundled fonts already have, incl. synthesized bold).

### Server

- **Model** (`app/models/common.py`): `UploadedFont`; add `uploaded_fonts: list[UploadedFont] = Field(default_factory=list)` to `BrandProfile`. Client mirror in `types/index.ts`.
- **Service** (`app/services/workspace_service.py`): `add_workspace_font` / `remove_workspace_font` (mirror `add/remove_workspace_image`), and `resolve_uploaded_font(brand_profile, family) -> storage_key | None`.
- **Routes** (`app/routes/workspaces.py`): `POST /{id}/fonts` (multipart `file` + `name`; `.ttf` only → 415 otherwise; 5 MB cap; cap-8 → 409; family deduped per workspace; demo-blocked), `DELETE /{id}/fonts/{font_id}` (demo-blocked, deletes bytes), `GET /{id}/fonts/file/{font_id}/{filename}` (serve bytes, `font/ttf`, auth-gated via `get_workspace_or_404` — mirrors the image serve route's traversal-safe key rebuild). Storage key via the existing `build_image_key` pattern (or a `build_font_key`).
- **PDF** (`app/services/document_service.py`): `_register_pdf_font` first resolves an uploaded font for the family (read bytes from storage → `io.BytesIO` → `TTFont(name, BytesIO)`, no temp file); else the existing bundled `resolve_font_file`; else serif/sans. This is what makes parity real. (Needs the workspace `brand_profile` + storage threaded into the registration step.)

### Client — cards (the source-aware loader)

`brandFonts.ts` functions gain the workspace's uploaded fonts (a `family → url` map):
- For a family in `uploaded_fonts`: **fetch the bytes auth-gated** (bearer token, like `fetchImageDataUrl`) → an `ArrayBuffer` (Satori) + a **data-URL `@font-face`** (DOM preview, since an auth-gated URL can't be used directly in CSS `url()`).
- Else: the existing CDN-by-name path, unchanged.
- A small `fetchFontBuffer(url) -> ArrayBuffer` (auth-gated) in the api layer. Callers thread `uploaded_fonts`: `useCardExport` (Satori), `CardPreview`/`cardElement` + `DeckPreview` (DOM), and the editor `FontPreview`.

### Client — picker + management

- **Settings → Brand fonts** (new section, mirrors Brand images): upload (file + name), list, delete; demo-aware. New `api/workspaces` hooks `useAddFont`/`useRemoveFont`.
- The font `<Select>` (`optionsForRole`) also lists the workspace's uploaded font families (applicable to **any** role), so after uploading you pick it for Heading/Body/Mono and Save.

## Error / edge handling

- Non-`.ttf` → 415; empty → 400; >5 MB → 413; over cap → 409; duplicate family → 409 (or reject in UI). Demo → 403 on add/delete; selecting + rendering an uploaded font is fine for demo (no mutation) but the demo workspace seeds none.
- An uploaded family not found at render time (deleted after selection): cards fall back to `Georgia`, PDF to serif/sans — the existing fallbacks, no crash. A bad font file that ReportLab can't register is caught (existing `except`) → serif/sans fallback, never breaks rendering.
- Name precedence: an uploaded family shadows a catalog family of the same name (workspace-specific wins); documented.

## Testing

- **Server:** `add/remove_workspace_font` + routes (add/list-via-workspace/delete/cap/demo/cross-owner/415); `resolve_uploaded_font`; `_register_pdf_font` embeds an uploaded TTF (use a tiny real TTF fixture, e.g. a bundled one's bytes) vs. falls back. Serve route returns the bytes auth-gated.
- **Client:** `optionsForRole` includes uploaded families; the source-aware loader picks the uploaded path for an uploaded family and the CDN path otherwise (unit-test the resolver decision with `fetch` mocked); the Settings section add/delete request shapes.

## Scope note

This is the largest feature of the session (server + a real client-loader change + PDF + Settings). Intended as **one cohesive PR** to avoid an awkward "PDF embeds but cards fall back" half-state on `dev`; if the plan proves unwieldy it can split into (1) server + management + picker + PDF and (2) the card-loader source-awareness.

## Out of scope / fast-follows

`.otf`/`.woff2` via a `fontTools` CFF→TTF conversion; multi-weight uploads (regular + bold + italic); reading the font's real family name; self-hosting the curated catalog fonts to drop the CDN.
