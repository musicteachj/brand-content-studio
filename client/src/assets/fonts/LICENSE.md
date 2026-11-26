# Bundled card fonts

Lora (regular 400 and bold 700, Latin subset), licensed under the SIL Open Font
License (OFL), retrieved from the fontsource CDN
(`cdn.jsdelivr.net/fontsource/fonts/lora@latest/latin-<weight>-normal.ttf`),
which mirrors Google Fonts.

It ships with the client so a card always has a font to render and export with:
it's the default when a workspace sets no brand font, and the stand-in when a
brand font can't be loaded (see `src/styles/brandFonts.ts`).

## Superscript and subscript digits

`folio-card-scripts-400.ttf` and `folio-card-scripts-700.ttf` are cut from Noto
Serif (SIL Open Font License, OFL), retrieved from the fontsource CDN
(`cdn.jsdelivr.net/fontsource/fonts/noto-serif@latest/math-<weight>-normal.ttf`)
and subset with fontTools to U+2070-209F (superscript and subscript digits and
signs, about 5 KB each). The card fonts' Latin subsets don't include these, so
without them "CO₂" exports with a placeholder box. They sit last in Satori's font
list, so they're only used for characters the brand face lacks.

## Common symbols

`folio-card-symbols-400.ttf` is cut from Noto Sans Math (SIL Open Font License,
OFL), retrieved from the fontsource CDN
(`cdn.jsdelivr.net/fontsource/fonts/noto-sans-math@latest/latin-400-normal.ttf`)
and subset with fontTools to 26 characters that turn up in marketing copy:
arrows (← ↑ → ↓ ↔ ↕ ↖ ↗ ↘ ↙ ⇒ ⇔), comparison and math signs (≈ ≠ ≡ ≤ ≥ ≪ ≫ ∑ ∓ √
∝ ∞ ∴) and ✓, about 5 KB. Like the scripts font, it's last in Satori's list and
only used for characters the brand face lacks.
