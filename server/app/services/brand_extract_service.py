"""Brand auto-extraction (Phase 4c). Two steps:

  1. `extract_palette` — Pillow quantizes the uploaded image to its dominant
     colors and returns exact hexes (deterministic, no network — unit-testable).
  2. `BrandExtractService.propose`: one Claude **vision** call with structured
     output (JSON matching the strict schema; the image + the detected hexes as
     hints) returns a *proposed* brand profile: named/role-assigned colors + a
     voice summary + best-effort fonts.

The proposal is returned to the client for review and is **never auto-applied**
(it lands via the existing brand PATCH once the user accepts). The request
shape is shared with `ai_service` through `claude_calls` (DECISIONS #40)."""
from __future__ import annotations

import asyncio
import base64
import io
from typing import Any, cast

from PIL import Image
from pydantic import ValidationError

from app.models.common import BrandColor, BrandFonts
from app.models.workspace import BrandExtractResponse
from app.prompts.brand_extract import (
    BRAND_EXTRACT_TOOL,
    EXEMPLAR_NOTE_TOOL,
    build_exemplar_system,
    build_exemplar_user,
    build_extract_system,
    build_extract_user,
)
from app.services import claude_calls
from app.services.ai_clients import get_anthropic
from app.services.ai_ledger import LineRequest
from app.services.ai_meter import MeteredLine
from app.services.brand_fonts import curated_family

# A ceiling with room for adaptive thinking and Sonnet 5.x's larger token counts.
EXTRACT_MAX_TOKENS = 4000
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
    """Shape the structured-output result into the typed proposal. Colors with an invalid
    hex are dropped (one bad value mustn't lose the whole proposal), and the
    palette falls back to the detected hexes if none survive. Fonts keep only
    curated families (canonical spelling), so a style description like "Clean
    sans-serif" can never become a brand font the card renderer can't load."""
    raw_colors = tool_result.get("colors") or []
    colors: list[BrandColor] = []
    for c in raw_colors:
        hex_ = str(c.get("hex", "")).strip()
        name = str(c.get("name", "")).strip()
        role = c.get("role", "primary")
        if not hex_:
            continue
        try:
            colors.append(BrandColor(name=name or hex_, hex=hex_, role=role))
        except ValidationError:
            continue
    if not colors:
        colors = [BrandColor(name=h, hex=h, role="primary") for h in detected_hexes]

    fonts_raw = tool_result.get("fonts") or {}
    fonts = BrandFonts(
        heading=curated_family(str(fonts_raw.get("heading", ""))),
        body=curated_family(str(fonts_raw.get("body", ""))),
        mono=curated_family(str(fonts_raw.get("mono", "")), mono=True),
    )
    voice = str(tool_result.get("voice_summary", "")).strip() or None
    return BrandExtractResponse(colors=colors, voice_summary=voice, fonts=fonts)


def _vision_content(user: str, *, image_b64: str, media_type: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": image_b64},
        },
        {"type": "text", "text": user},
    ]


def _vision_line(purpose: str, system: str, user: str, tool: dict[str, Any]) -> LineRequest:
    # The image counts as IMAGE_TOKEN_BOUND whatever its bytes, so a placeholder stands in.
    return claude_calls.structured_line(
        purpose,
        system=system,
        content=_vision_content(user, image_b64="", media_type="image/png"),
        tool=tool,
        max_tokens=EXTRACT_MAX_TOKENS,
    )


def brand_extract_line(data: bytes) -> LineRequest:
    """The reservation for `BrandExtractService.propose` on this image."""
    return _vision_line(
        "brand_extract",
        build_extract_system(),
        build_extract_user(extract_palette(data)),
        BRAND_EXTRACT_TOOL,
    )


def exemplar_note_line() -> LineRequest:
    """The reservation for `BrandExtractService.propose_exemplar_note`."""
    return _vision_line(
        "exemplar_note", build_exemplar_system(), build_exemplar_user(), EXEMPLAR_NOTE_TOOL
    )


class BrandExtractService:
    """Instantiated per-request via FastAPI `Depends()` (zero-arg), matching the
    `GenerationService` convention. Each method takes the ledger line its route reserved."""

    def __init__(self) -> None:
        self.client = get_anthropic()

    async def propose(self, data: bytes, media_type: str, *, line: MeteredLine) -> BrandExtractResponse:
        detected = await asyncio.to_thread(extract_palette, data)  # Pillow work, off the loop
        result = await self._vision_structured_call(
            system=build_extract_system(),
            user=build_extract_user(detected),
            image_b64=base64.standard_b64encode(data).decode("ascii"),
            media_type=media_type,
            tool=BRAND_EXTRACT_TOOL,
            line=line,
        )
        return build_extract_response(detected, result)

    async def propose_exemplar_note(self, data: bytes, media_type: str, *, line: MeteredLine) -> str:
        """One vision call with structured output → a short style note for an uploaded card."""
        result = await self._vision_structured_call(
            system=build_exemplar_system(),
            user=build_exemplar_user(),
            image_b64=base64.standard_b64encode(data).decode("ascii"),
            media_type=media_type,
            tool=EXEMPLAR_NOTE_TOOL,
            line=line,
        )
        return str(result.get("style_note", "")).strip()

    async def _vision_structured_call(
        self,
        *,
        system: str,
        user: str,
        image_b64: str,
        media_type: str,
        tool: dict[str, Any],
        line: MeteredLine,
    ) -> dict[str, Any]:
        return await claude_calls.structured_call(
            self.client,
            system=system,
            content=_vision_content(user, image_b64=image_b64, media_type=media_type),
            tool=tool,
            max_tokens=EXTRACT_MAX_TOKENS,
            line=line,
        )
