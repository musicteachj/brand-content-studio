"""The public examples page's payload. A module of its own because it joins the brand
models (`common`, which imports `generation`) with `GenerationResponse`."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.common import BrandColor, BrandFonts
from app.models.generation import GenerationResponse


class ExampleBrand(BaseModel):
    """The part of the demo brand profile the examples page shows."""

    colors: list[BrandColor] = Field(default_factory=list)
    fonts: BrandFonts = Field(default_factory=BrandFonts)
    accent_hex: str | None = None
    voice_summary: str | None = None


class ExamplesResponse(BaseModel):
    workspace_name: str = ""
    brand: ExampleBrand = Field(default_factory=ExampleBrand)
    items: list[GenerationResponse] = Field(default_factory=list)
