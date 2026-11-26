"""Parity guards for the curated brand-font set: every serif/sans family the picker
offers must have a bundled TTF (so a font chosen for a card also embeds in an
exported PDF), and the server's curated list must match the client's catalog (so
brand extract can propose exactly what the picker offers)."""
import re
from pathlib import Path

from app.services.brand_fonts import CURATED_MONO_FAMILIES, CURATED_TEXT_FAMILIES, resolve_font_file

FONT_CATALOG = Path(__file__).resolve().parents[2] / "client" / "src" / "styles" / "fontCatalog.ts"


def _client_catalog() -> dict[str, set[str]]:
    # Each entry starts `{ family: "...", category: "..."` (later fields, such as
    # `weights`, may follow).
    entries = re.findall(r'\{\s*family:\s*"([^"]+)",\s*category:\s*"(serif|sans|mono)"', FONT_CATALOG.read_text())
    out: dict[str, set[str]] = {"text": set(), "mono": set()}
    for family, category in entries:
        out["mono" if category == "mono" else "text"].add(family)
    return out


def test_curated_families_have_bundled_ttf():
    missing = [fam for fam in CURATED_TEXT_FAMILIES if resolve_font_file(fam) is None]
    assert missing == [], f"missing bundled TTFs for: {missing}"


def test_server_curated_list_matches_client_catalog():
    catalog = _client_catalog()
    assert catalog["text"], "parsed no families from fontCatalog.ts"
    assert set(CURATED_TEXT_FAMILIES) == catalog["text"]
    assert set(CURATED_MONO_FAMILIES) == catalog["mono"]
