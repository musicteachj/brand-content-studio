"""Generation models. Phase 1a covers `type == "text"` (LinkedIn posts);
`card` is added in Phase 1b. Each generation snapshots its retrieval so the
debug panel survives later asset deletes/re-ingests (DATA_MODEL.md)."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

import re

from pydantic import BaseModel, Field, field_validator

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


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


class CardTemplate(str, Enum):
    """The three card archetypes (DESIGN §4 template picker). The user picks one
    explicitly — there is no auto-select."""

    photo_led = "photo-led"
    statement = "statement"
    quote = "quote"


class TextGenerateRequest(BaseModel):
    brief: str = Field(min_length=3, max_length=2000)
    tone: Tone = Tone.default
    length: Length = Length.medium


class CardGenerateRequest(BaseModel):
    brief: str = Field(min_length=3, max_length=2000)
    template_id: CardTemplate = CardTemplate.photo_led
    tone: Tone = Tone.default


class TextOutput(BaseModel):
    post_text: str
    hashtags: list[str] = Field(default_factory=list)
    char_count: int = 0


class CardFields(BaseModel):
    """The structured card copy, obtained via Anthropic tool-use (not parsed from
    the stream — ARCHITECTURE gotcha #8)."""

    eyebrow: str = ""
    headline: str = ""
    body: str = ""
    cta: str = ""
    hashtag: str = ""


class ImageAttribution(BaseModel):
    """Required when an image's source is Unsplash — rendered on the card AND in
    the picker (license requirement, ARCHITECTURE gotcha #4)."""

    author: str
    author_url: str
    source_url: str


class CardImage(BaseModel):
    source: str  # "unsplash" | "upload"
    url: Optional[str] = None
    storage_key: Optional[str] = None
    unsplash_id: Optional[str] = None
    attribution: Optional[ImageAttribution] = None  # required when source == "unsplash"


class CardOutput(BaseModel):
    template_id: CardTemplate = CardTemplate.photo_led
    fields: CardFields = Field(default_factory=CardFields)
    image: Optional[CardImage] = None
    suggested_keywords: list[str] = Field(default_factory=list)
    # Phase 1.5: which brand-palette color this card uses as its accent. Null =
    # fall back to the brand's default accent role. Validated against the
    # workspace palette in the PATCH route (membership needs the workspace).
    accent_hex: Optional[str] = None


class GenerationUpdate(BaseModel):
    """Partial update applied to a card generation's `output` — Phase 1b attaches
    the selected image; Phase 1.5 adds inline field/template edits + the per-card
    accent. Every field is client-side customization: no `/generate` call."""

    template_id: Optional[CardTemplate] = None
    fields: Optional[CardFields] = None
    image: Optional[CardImage] = None
    accent_hex: Optional[str] = None

    @field_validator("accent_hex")
    @classmethod
    def _valid_hex(cls, v: Optional[str]) -> Optional[str]:
        # Shape-check only here; palette membership is enforced in the route,
        # which has the workspace's brand colors.
        if v is not None and not _HEX_RE.match(v):
            raise ValueError("accent_hex must be a hex color like #1C3A2E")
        return v


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
