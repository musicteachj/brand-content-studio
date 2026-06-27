"""Parity guard: every curated serif/sans family the picker offers must have a
bundled TTF, so a font chosen for a card also embeds in an exported PDF."""
from app.services.brand_fonts import resolve_font_file

# Mirror the serif/sans entries of client/src/styles/fontCatalog.ts (keep in sync).
CURATED_PDF_FAMILIES = [
    "DM Serif Display",
    "Playfair Display",
    "Fraunces",
    "Spectral",
    "Lora",
    "Inter",
    "Work Sans",
    "Libre Franklin",
    "Archivo",
]


def test_curated_families_have_bundled_ttf():
    missing = [fam for fam in CURATED_PDF_FAMILIES if resolve_font_file(fam) is None]
    assert missing == [], f"missing bundled TTFs for: {missing}"
