"""Brand-font resolution for document rendering (Phase 2).

The PDF renderer can embed a workspace's real brand fonts, but only when the TTF
is available locally — we deliberately do **not** fetch fonts over the network at
request time (that would add an SSRF/availability surface to a hot path). Drop
`<font-slug>.ttf` files into `settings.brand_fonts_dir` to enable embedding;
anything missing falls back to a serif/sans base font keyed by name. The .docx
renderer doesn't need the binary — it references the font by name and Word
substitutes — so brand fonts always apply there.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.config import settings

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Family-name fragments that signal a serif face (so the fallback picks a serif
# base font rather than a sans one). Lower-cased substring match.
_SERIF_HINTS = (
    "serif",  # excluding "sans serif" — handled below
    "times",
    "georgia",
    "garamond",
    "spectral",
    "playfair",
    "merriweather",
    "lora",
    "pt serif",
    "source serif",
    "crimson",
    "libre baskerville",
    "cormorant",
)


# The curated brand-font set, mirroring client/src/styles/fontCatalog.ts.
# Heading/body pick from serif + sans; mono from mono. tests/test_brand_fonts.py
# fails if this drifts from the client catalog or a serif/sans family lacks a
# bundled TTF for PDF parity.
CURATED_TEXT_FAMILIES: tuple[str, ...] = (
    "DM Serif Display",
    "Playfair Display",
    "Fraunces",
    "Spectral",
    "Lora",
    "Inter",
    "Work Sans",
    "Libre Franklin",
    "Archivo",
)
CURATED_MONO_FAMILIES: tuple[str, ...] = ("JetBrains Mono", "IBM Plex Mono")


def curated_family(name: str | None, *, mono: bool = False) -> str | None:
    """Canonical curated family for a (case-insensitive) name, or None if it isn't
    one. `mono` selects the mono set; otherwise the heading/body set."""
    if not name or not name.strip():
        return None
    wanted = name.strip().lower()
    pool = CURATED_MONO_FAMILIES if mono else CURATED_TEXT_FAMILIES
    return next((f for f in pool if f.lower() == wanted), None)


def font_slug(family: str) -> str:
    """`"DM Serif Display"` -> `"dm-serif-display"` — the on-disk TTF basename."""
    return _SLUG_RE.sub("-", family.strip().lower()).strip("-")


def resolve_font_file(family: str | None) -> str | None:
    """Return the path to a bundled/cached TTF for `family`, or None to fall back.
    Confined to `brand_fonts_dir` so a crafted family name can't escape it."""
    if not family or not family.strip():
        return None
    slug = font_slug(family)
    if not slug:
        return None
    root = Path(settings.brand_fonts_dir).resolve()
    candidate = (root / f"{slug}.ttf").resolve()
    if root != candidate and root not in candidate.parents:
        return None  # escaped the fonts dir — reject
    return str(candidate) if candidate.is_file() else None


def is_serif(family: str | None) -> bool:
    """Heuristic for the PDF fallback: does this family read as a serif face?"""
    if not family:
        return True  # documents default to serif when unspecified
    name = family.strip().lower()
    if "sans" in name:
        return False
    return any(hint in name for hint in _SERIF_HINTS) or "display" in name
