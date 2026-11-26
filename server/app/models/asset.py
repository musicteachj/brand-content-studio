"""Asset models. An asset is one uploaded brand document; ingestion turns it
into retrievable chunks in the vector store (chunk text/vectors never touch Mongo)."""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class AssetKind(str, Enum):
    voice = "voice"
    posts = "posts"
    pillars = "pillars"
    personas = "personas"
    competitors = "competitors"
    other = "other"


class IngestionStatus(str, Enum):
    processing = "processing"
    ready = "ready"
    error = "error"


class AssetResponse(BaseModel):
    id: str
    workspace_id: str
    filename: str
    content_type: str
    asset_kind: AssetKind
    size_bytes: int
    ingestion_status: IngestionStatus
    chunk_count: int = 0
    error: str | None = None
    ingested_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AssetPage(BaseModel):
    items: list[AssetResponse]
    next_offset: int | None = None
