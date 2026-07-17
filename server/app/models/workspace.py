"""Workspace models. One brand corpus per workspace; owned by a single user."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.common import _HEX_RE, BrandColor, BrandFonts, BrandProfile
from app.models.generation import CardTemplate


class BrandExtractResponse(BaseModel):
    """A *proposed* brand profile inferred from an uploaded image (Phase 4c).
    Returned for client review; never persisted directly — the user accepts it
    into the brand editor, which saves via the existing brand PATCH."""

    colors: list[BrandColor] = Field(default_factory=list)
    voice_summary: str | None = None
    fonts: BrandFonts = Field(default_factory=BrandFonts)


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    brand_profile: BrandProfile = Field(default_factory=BrandProfile)


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    brand_profile: BrandProfile | None = None


class BrandImageRename(BaseModel):
    name: str = Field(default="", max_length=500)  # clamped to 80 in the service


class CardPresetCreate(BaseModel):
    """Request body for adding a card preset. `id` is server-derived; `accent_hex`
    is shape-validated here so a bad hex is a 422 at the boundary (not a 500 from
    building the `CardPreset` in the route)."""

    name: str = Field(default="", max_length=500)  # clamped to 80 in the route
    template_id: CardTemplate
    accent_hex: str | None = None

    @field_validator("accent_hex")
    @classmethod
    def _valid_hex(cls, v: str | None) -> str | None:
        if v is not None and not _HEX_RE.match(v):
            raise ValueError("accent_hex must be a hex color like #1C3A2E")
        return v


class WorkspaceResponse(BaseModel):
    id: str
    owner_id: str
    name: str
    slug: str
    brand_profile: BrandProfile
    vector_namespace: str
    embedding_model: str
    embedding_dim: int
    asset_count: int = 0
    ready_chunk_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
