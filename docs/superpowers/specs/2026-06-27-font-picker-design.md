# Curated Font Picker + PDF Parity — Design

**Goal:** Replace the free-text brand-font inputs with a **curated picker** over a small vetted set of OFL fonts, and **bundle that set's TTFs** so a chosen font renders the same on a card *and* embeds in an exported PDF. Closes today's gaps: typo-prone free text that silently falls back to Georgia, and the card↔PDF asymmetry (a card font isn't embedded in PDFs unless its TTF happens to be bundled).

**Non-goals:** User font-file **upload** (deferred — expensive, niche); removing the runtime fontsource **CDN** dependency for cards (cards keep loading via the CDN as today); changing the stored shape (`brand_profile.fonts` stays `{heading, body, mono}` family-name strings).

## Background (current state)

- `BrandIdentityEditor.tsx` exposes `fonts.heading/body/mono` as **free-text `<Input>`s**.
- **Cards:** `client/src/styles/brandFonts.ts` slugifies the family name and fetches its TTF from the fontsource CDN at render time; an unknown name 404s → Satori falls back to `Georgia, serif`. Effectively any Google-Fonts family works on cards; nothing validates it.
- **PDF (documents):** `server/app/services/brand_fonts.py:resolve_font_file` maps a family → `{font_slug(family)}.ttf` in `settings.brand_fonts_dir` (`server/app/assets/fonts/`), else a serif/sans fallback. **No runtime network fetch** (SSRF-safe). Only `dm-serif-display.ttf` + `spectral.ttf` are bundled today.
- Verdure (demo) uses `heading: "DM Serif Display"`, `body: "Spectral"` (both bundled).

## The curated set (~11 OFL Google Fonts)

All are SIL Open Font License → free to bundle/commit.

- **Serif:** DM Serif Display, Playfair Display, Fraunces, Spectral, Lora
- **Sans:** Inter, Work Sans, Libre Franklin, Archivo
- **Mono:** JetBrains Mono, IBM Plex Mono

Each catalog entry: `{ family, category: "serif" | "sans" | "mono" }`. Heading & Body select from serif+sans (9); Mono from mono (2). Verdure's pair is included, so the demo keeps embedding.

## Design

### Client (A) — picker replaces free text

- **New** `client/src/styles/fontCatalog.ts`: `export const FONT_OPTIONS: { family: string; category: "serif" | "sans" | "mono" }[]` (the set above), plus helpers `headingBodyOptions()` (serif+sans) and `monoOptions()` (mono).
- **`BrandIdentityEditor.tsx`:** the three `<Input>`s become `<Select>`s (existing `@/components/ui/select`) bound to the same `register("fonts.heading|body|mono")` string values, with an empty **"Default"** option (`""` → stored `null`). Filtered by role.
- **Live preview:** under each select, one line of sample text rendered in the chosen family, reusing `injectBrandFontFaces` from `brandFonts.ts` so the preview uses the real font (same source as the card).
- **Legacy/custom value preservation:** if the stored value isn't in the catalog, prepend it as a `"<name> (current)"` option so a Select never drops saved data. Still renders on cards via CDN; won't embed in PDF (the one residual non-parity case).
- **Brand auto-extract Apply:** `applyProposal` maps each proposed font name to a catalog family by case-insensitive match; on no match, keep the proposed name as a "(current)" custom value (no behavior regression).

### Server (C) — bundle the set's TTFs

- Add each curated **serif/sans** family's regular-weight TTF to `server/app/assets/fonts/`, named `{font_slug(family)}.ttf` (e.g. `playfair-display.ttf`, `inter.ttf`, `lora.ttf`, …). `dm-serif-display.ttf` + `spectral.ttf` already exist. `resolve_font_file` then finds them → PDFs embed the real font. No code change to the resolver.
- **Mono is metadata-only** — it has no card/PDF render path today, so mono TTFs are **not** bundled.
- Add a short `server/app/assets/fonts/LICENSE.md` noting each font + its OFL source.

### Implementation dependency (acquiring the TTFs)

The ~9 new TTFs must be fetched **at implementation time** (a build asset step, not runtime) from a stable OFL source (fontsource CDN `cdn.jsdelivr.net/fontsource/fonts/{slug}@latest/latin-400-normal.ttf`, or Google Fonts). If outbound network is unavailable in the work environment, this step needs the files provided out-of-band — flag and pause rather than ship picker options without their bundled TTFs.

## Error / edge handling

- Picked family always has a bundled TTF (enforced by the parity test) → PDF parity holds for every selectable serif/sans option.
- A legacy custom value renders on cards (CDN) and falls back to serif/sans in PDF — preserved, not dropped.
- Empty selection → `null` → existing fallbacks (`Georgia` on cards, serif/sans base in PDF) — unchanged.

## Testing

- **Client** (`fontCatalog` + editor): the picker lists the role-appropriate options; selecting sets the `fonts.*` value; a stored non-catalog value appears as a preserved "(current)" option.
- **Server** (parity guard): for every curated **serif/sans** family, `resolve_font_file(family)` returns a path (i.e., its TTF is bundled). A `CURATED_PDF_FAMILIES` list lives server-side for this test, mirroring `fontCatalog.ts`; a comment in both points at the other ("keep in sync"). Adding a picker font without bundling its TTF then fails CI.

## Out of scope

User font-file upload; self-hosting card fonts to drop the CDN dependency; mono in the PDF/card render path; per-weight bundling (one regular TTF per family is what `resolve_font_file` needs; cards continue to pull extra weights from the CDN).
