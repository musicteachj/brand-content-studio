"""Workspace models. One brand corpus per workspace; owned by a single user."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.common import BrandColor, BrandFonts, BrandProfile


class BrandExtractResponse(BaseModel):
    """A *proposed* brand profile inferred from an uploaded image (Phase 4c).
    Returned for client review; never persisted directly — the user accepts it
    into the brand editor, which saves via the existing brand PATCH."""

    colors: list[BrandColor] = Field(default_factory=list)
    voice_summary: Optional[str] = None
    fonts: BrandFonts = Field(default_factory=BrandFonts)


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    brand_profile: BrandProfile = Field(default_factory=BrandProfile)


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    brand_profile: Optional[BrandProfile] = None


class BrandImageRename(BaseModel):
    name: str = Field(default="", max_length=500)  # clamped to 80 in the service


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
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
