"""Generation models. Phase 1a covers `type == "text"` (LinkedIn posts);
`card` is added in Phase 1b. Each generation snapshots its retrieval so the
debug panel survives later asset deletes/re-ingests (DATA_MODEL.md)."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class GenerationType(str, Enum):
    text = "text"
    card = "card"


class GenerationStatus(str, Enum):
    complete = "complete"
    error = "error"


class Tone(str, Enum):
    default = "default"
    confident = "confident"
    warm = "warm"
    technical = "technical"
    provocative = "provocative"


class Length(str, Enum):
    short = "short"
    medium = "medium"
    long = "long"


class TextGenerateRequest(BaseModel):
    brief: str = Field(min_length=3, max_length=2000)
    tone: Tone = Tone.default
    length: Length = Length.medium


class TextOutput(BaseModel):
    post_text: str
    hashtags: list[str] = Field(default_factory=list)
    char_count: int = 0


class RetrievalMetaItem(BaseModel):
    """Per-chunk snapshot for the retrieval debug panel."""

    chunk_id: str
    asset_id: str
    filename: str
    asset_kind: str
    score: float
    preview: str  # ~240 chars of the matched text
    chunk_index: int
    page: Optional[int] = None
    pinned: bool = False  # always-injected brand fundamental (voice/pillars)


class GenerationResponse(BaseModel):
    id: str
    workspace_id: str
    owner_id: str
    type: GenerationType
    brief: str
    status: GenerationStatus
    output: dict[str, Any]  # discriminated by `type`; TextOutput for text
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    retrieval_meta: list[RetrievalMetaItem] = Field(default_factory=list)
    model: str
    embedding_query_model: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
