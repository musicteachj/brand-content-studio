"""Shared model pieces: brand profile + Mongo doc serialization helpers.

The app follows the EMS convention — models carry no `_id`; routes/services
serialize Mongo's ObjectId to a `str` `id` on the way out.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.models.generation import CardTemplate

ColorRole = Literal["primary", "secondary", "neutral", "accent"]
_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


class BrandColor(BaseModel):
    name: str
    hex: str
    role: ColorRole = "primary"

    @field_validator("hex")
    @classmethod
    def _valid_hex(cls, v: str) -> str:
        # Validate at the boundary so a direct API call can't store a junk hex the
        # client's regex would have caught (parity with CardPreset.accent_hex).
        if not _HEX_RE.match(v):
            raise ValueError("hex must be a color like #1C3A2E")
        return v


class BrandFonts(BaseModel):
    heading: str | None = None
    body: str | None = None
    mono: str | None = None


class BrandLogo(BaseModel):
    storage_key: str
    url: str | None = None


class BrandExemplar(BaseModel):
    """A past on-brand card the owner uploaded; we store the image + a short
    extracted style note that steers generation (Phase 4c)."""

    id: str
    storage_key: str
    url: str | None = None
    style_note: str


class BrandImage(BaseModel):
    """A reusable image the owner saved to the workspace's brand-image library,
    pickable as a card picture from the image picker (no model involvement —
    distinct from `BrandExemplar`, which steers generation via a style note)."""

    id: str
    storage_key: str
    url: str | None = None
    name: str | None = None  # original filename, for a picker label


class UploadedFont(BaseModel):
    """A `.ttf` the owner uploaded; usable as a brand font (`fonts.{heading,body,
    mono}` by family name) with full parity on cards + embedded in PDFs. The
    `family` is the user-given label — also the handle for @font-face / Satori /
    ReportLab (no font parsing)."""

    id: str
    family: str
    storage_key: str
    url: str | None = None


class CardPreset(BaseModel):
    """A named, reusable card *look* — the two per-card knobs (template + accent).
    Fonts/non-accent colors are workspace-global, so they're not part of a preset;
    the copy/brief/image are per-card. Applied from the card generate flow, managed
    in Settings (Phase 5 PR-B)."""

    id: str
    name: str
    template_id: CardTemplate
    accent_hex: str | None = None

    @field_validator("accent_hex")
    @classmethod
    def _valid_hex(cls, v: str | None) -> str | None:
        if v is not None and not _HEX_RE.match(v):
            raise ValueError("accent_hex must be a hex color like #1C3A2E")
        return v


class BrandProfile(BaseModel):
    """Workspace brand identity. These fonts/colors drive the card preview —
    never the app's own Folio chrome (DESIGN.md §7)."""

    colors: list[BrandColor] = Field(default_factory=list)
    accent_hex: str | None = None  # optional UI tint, cosmetic only
    fonts: BrandFonts = Field(default_factory=BrandFonts)
    logo: BrandLogo | None = None
    voice_summary: str | None = None  # cached blurb injected into the prompt header
    exemplars: list[BrandExemplar] = Field(default_factory=list)
    brand_images: list[BrandImage] = Field(default_factory=list)
    uploaded_fonts: list[UploadedFont] = Field(default_factory=list)
    card_presets: list[CardPreset] = Field(default_factory=list)


def serialize_doc(doc: dict[str, Any]) -> dict[str, Any]:
    """Copy a Mongo doc with `_id` -> `id` (str) and any nested ObjectIds cast
    to str, so it slots straight into a Pydantic response model."""
    out = dict(doc)
    if "_id" in out:
        out["id"] = str(out.pop("_id"))
    for key in ("owner_id", "workspace_id"):
        if key in out and out[key] is not None:
            out[key] = str(out[key])
    return out


def utcnow() -> datetime:
    from datetime import timezone

    return datetime.now(timezone.utc)
