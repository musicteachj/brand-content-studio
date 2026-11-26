"""Template models (Phase 5). Mirror server/app/models/* — no `_id`; routes
serialize ObjectId → str `id` on the way out."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TemplateFormat = Literal["docx", "pptx"]


class TemplateResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    format: TemplateFormat
    storage_key: str
    placeholders: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class TemplateRenderRequest(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


class TemplateAiFillRequest(BaseModel):
    brief: str = Field(min_length=1, max_length=2000)


class TemplateAiFillResponse(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)
