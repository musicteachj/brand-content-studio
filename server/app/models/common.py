"""Shared model pieces: brand profile + Mongo doc serialization helpers.

The app follows the EMS convention — models carry no `_id`; routes/services
serialize Mongo's ObjectId to a `str` `id` on the way out.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

ColorRole = Literal["primary", "secondary", "neutral", "accent"]


class BrandColor(BaseModel):
    name: str
    hex: str
    role: ColorRole = "primary"


class BrandFonts(BaseModel):
    heading: Optional[str] = None
    body: Optional[str] = None
    mono: Optional[str] = None


class BrandLogo(BaseModel):
    storage_key: str
    url: Optional[str] = None


class BrandProfile(BaseModel):
    """Workspace brand identity. These fonts/colors drive the card preview —
    never the app's own Folio chrome (DESIGN.md §7)."""

    colors: list[BrandColor] = Field(default_factory=list)
    accent_hex: Optional[str] = None  # optional UI tint, cosmetic only
    fonts: BrandFonts = Field(default_factory=BrandFonts)
    logo: Optional[BrandLogo] = None
    voice_summary: Optional[str] = None  # cached blurb injected into the prompt header


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
