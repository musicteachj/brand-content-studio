"""Workspace models. One brand corpus per workspace; owned by a single user."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.common import BrandProfile


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    brand_profile: BrandProfile = Field(default_factory=BrandProfile)


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    brand_profile: Optional[BrandProfile] = None


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
