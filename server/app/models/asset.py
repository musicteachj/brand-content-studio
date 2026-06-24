"""Asset models. An asset is one uploaded brand document; ingestion turns it
into retrievable chunks in the vector store (chunk text/vectors never touch Mongo)."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

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
    error: Optional[str] = None
    ingested_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
