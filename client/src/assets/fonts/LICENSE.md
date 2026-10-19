# Bundled card fallback font

Lora (regular 400 and bold 700, Latin subset), licensed under the SIL Open Font
License (OFL), retrieved from the fontsource CDN
(`cdn.jsdelivr.net/fontsource/fonts/lora@latest/latin-<weight>-normal.ttf`),
which mirrors Google Fonts.

It ships with the client so a card always has a font to render and export with:
it's the default when a workspace sets no brand font, and the stand-in when a
brand font can't be loaded (see `src/styles/brandFonts.ts`).
