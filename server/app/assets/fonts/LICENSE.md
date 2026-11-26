# Bundled brand fonts

These TTFs are bundled so the PDF renderer can embed a workspace's brand font
locally (no runtime fetch — see `app/services/brand_fonts.py`). All are licensed
under the SIL Open Font License (OFL), retrieved from the fontsource CDN
(`cdn.jsdelivr.net/fontsource/fonts/<slug>@latest/latin-400-normal.ttf`), which
mirrors Google Fonts.

- DM Serif Display — OFL
- Playfair Display — OFL
- Fraunces — OFL
- Spectral — OFL
- Lora — OFL
- Inter — OFL
- Work Sans — OFL
- Libre Franklin — OFL
- Archivo — OFL

The curated set is defined in `client/src/styles/fontCatalog.ts` (serif/sans
families must have a TTF here — guarded by `server/tests/test_brand_fonts.py`).
Mono families (JetBrains Mono, IBM Plex Mono) are metadata-only and not bundled.
