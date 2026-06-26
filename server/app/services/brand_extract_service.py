"""Brand auto-extraction (Phase 4c). Two steps:

  1. `extract_palette` — Pillow quantizes the uploaded image to its dominant
     colors and returns exact hexes (deterministic, no network — unit-testable).
  2. `BrandExtractService.propose` — a forced, strict Claude **vision** tool-use
     call (the image + the detected hexes as hints) returns a *proposed* brand
     profile: named/role-assigned colors + a voice summary + best-effort fonts.

The proposal is returned to the client for review and is **never auto-applied**
(it lands via the existing brand PATCH once the user accepts). Mirrors the
tool-use pattern in `generation_service` (ARCHITECTURE gotcha #8)."""
from __future__ import annotations

import base64
import io
from typing import Any, cast

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam, ToolChoiceToolParam, ToolParam
from PIL import Image

from app.config import settings
from app.models.common import BrandColor, BrandFonts
from app.models.workspace import BrandExtractResponse
from app.prompts.brand_extract import (
    BRAND_EXTRACT_TOOL,
    build_extract_system,
    build_extract_user,
)

EXTRACT_MAX_TOKENS = 800
_PALETTE_MAX = 6
_THUMB = 200  # downscale before quantizing — speed, and averages out JPEG noise


def extract_palette(data: bytes, max_colors: int = _PALETTE_MAX) -> list[str]:
    """Dominant colors as `#RRGGBB`, most-common first. Deterministic per image."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((_THUMB, _THUMB))
    quant = img.quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT)
    palette = quant.getpalette() or []
    # [(count, palette_index), ...] — PIL types the index loosely, so pin it.
    counts = cast("list[tuple[int, int]]", quant.getcolors() or [])
    hexes: list[str] = []
    seen: set[str] = set()
    for _count, idx in sorted(counts, key=lambda c: c[0], reverse=True):
        r, g, b = palette[idx * 3 : idx * 3 + 3]
        hex_ = f"#{r:02X}{g:02X}{b:02X}"
        if hex_ not in seen:
            seen.add(hex_)
            hexes.append(hex_)
    return hexes[:max_colors]


def build_extract_response(detected_hexes: list[str], tool_result: dict[str, Any]) -> BrandExtractResponse:
    """Shape the tool-use result into the typed proposal. Colors fall back to the
    detected palette if the model returns none; empty font/voice strings → None."""
    raw_colors = tool_result.get("colors") or []
    colors: list[BrandColor] = []
    for c in raw_colors:
        hex_ = str(c.get("hex", "")).strip()
        name = str(c.get("name", "")).strip()
        role = c.get("role", "primary")
        if hex_:
            colors.append(BrandColor(name=name or hex_, hex=hex_, role=role))
    if not colors:
        colors = [BrandColor(name=h, hex=h, role="primary") for h in detected_hexes]

    fonts_raw = tool_result.get("fonts") or {}
    fonts = BrandFonts(
        heading=(str(fonts_raw.get("heading", "")).strip() or None),
        body=(str(fonts_raw.get("body", "")).strip() or None),
        mono=(str(fonts_raw.get("mono", "")).strip() or None),
    )
    voice = str(tool_result.get("voice_summary", "")).strip() or None
    return BrandExtractResponse(colors=colors, voice_summary=voice, fonts=fonts)


class BrandExtractService:
    """Instantiated per-request via FastAPI `Depends()` (zero-arg), matching the
    `GenerationService` convention."""

    def __init__(self) -> None:
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def propose(self, data: bytes, media_type: str) -> BrandExtractResponse:
        detected = extract_palette(data)
        result = await self._vision_tool_call(
            system=build_extract_system(),
            user=build_extract_user(detected),
            image_b64=base64.standard_b64encode(data).decode("ascii"),
            media_type=media_type,
        )
        return build_extract_response(detected, result)

    async def _vision_tool_call(
        self, system: str, user: str, image_b64: str, media_type: str
    ) -> dict[str, Any]:
        message = await self.client.messages.create(
            model=settings.ai_model,
            max_tokens=EXTRACT_MAX_TOKENS,
            system=system,
            tools=[cast(ToolParam, BRAND_EXTRACT_TOOL)],
            tool_choice=cast(
                ToolChoiceToolParam, {"type": "tool", "name": BRAND_EXTRACT_TOOL["name"]}
            ),
            messages=cast(
                "list[MessageParam]",
                [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_b64,
                                },
                            },
                            {"type": "text", "text": user},
                        ],
                    }
                ],
            ),
        )
        for block in message.content:
            if block.type == "tool_use":
                return dict(block.input)  # type: ignore[arg-type]
        raise RuntimeError("Model did not return the brand_profile tool call.")
