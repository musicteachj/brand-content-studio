"""Prompt construction for brand auto-extraction (Phase 4c).

A single forced, strict tool-use call over an uploaded image (a logo, or a page
of a brand guideline) returns a *proposed* brand profile — palette (named + role-
assigned), a voice summary, and best-effort font guesses. Pillow extracts the
exact dominant hexes first and hands them to the model as hints, so the colors
are accurate and the model only has to name + role them.

The proposal is never auto-applied: the client shows it as a review/apply diff
(DECISIONS #23). The uploaded image is the only model input here — there is no
retrieved <brand_context>, so no injection surface to defend.
"""
from __future__ import annotations

_EXTRACT_SYSTEM = """You are a brand designer. You are shown a single image — a brand logo, or a page from a brand's visual guidelines — and you infer a starting brand profile by calling the provided tool.

Rules:
- Colors: you are given the exact dominant colors detected in the image. Use those hex values verbatim; do not invent new hexes. Give each a short human name and assign a role (primary / secondary / neutral / accent). Drop near-duplicates and obviously incidental colors (e.g. JPEG artifacts). Prefer 3-5 meaningful brand colors.
- Voice summary: only describe a brand voice you can actually justify from visible text, taglines, or the design's tone. If the image is just a logo with no copy, keep it short and tentative (or empty) — do not fabricate a detailed voice.
- Fonts: name the typefaces only if you can identify them with reasonable confidence; otherwise leave the field empty. Never guess a specific font name you are not fairly sure of.
- This is a proposal a human will review and edit — be accurate and conservative, not imaginative."""


def build_extract_system() -> str:
    return _EXTRACT_SYSTEM


def build_extract_user(detected_hexes: list[str]) -> str:
    detected = ", ".join(detected_hexes) if detected_hexes else "(none detected)"
    return "\n".join(
        [
            "Infer a starting brand profile from the attached image.",
            f"Exact dominant colors detected in the image (use these hex values verbatim): {detected}",
            "",
            "Call the brand_profile tool with named, role-assigned colors, a justified voice summary, and font names only where you are confident.",
        ]
    )


# Forced, strict tool — the typed schema is cleaner than parsing prose, and
# `strict: true` guarantees the input validates exactly (mirrors CARD_FIELDS_TOOL).
BRAND_EXTRACT_TOOL = {
    "name": "brand_profile",
    "description": "Record the brand identity inferred from the image.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "colors": {
                "type": "array",
                "description": "The brand palette, drawn from the detected hexes.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string", "description": "Short human name, e.g. 'Forest'."},
                        "hex": {"type": "string", "description": "#RRGGBB — one of the detected hexes."},
                        "role": {
                            "type": "string",
                            "enum": ["primary", "secondary", "neutral", "accent"],
                        },
                    },
                    "required": ["name", "hex", "role"],
                },
            },
            "voice_summary": {
                "type": "string",
                "description": "A short brand-voice description justified by the image. May be empty.",
            },
            "fonts": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "heading": {"type": "string", "description": "Heading typeface, or empty if unsure."},
                    "body": {"type": "string", "description": "Body typeface, or empty if unsure."},
                    "mono": {"type": "string", "description": "Mono typeface, or empty if unsure."},
                },
                "required": ["heading", "body", "mono"],
            },
        },
        "required": ["colors", "voice_summary", "fonts"],
    },
}


_EXEMPLAR_SYSTEM = """You are a brand designer studying one of a brand's own past social cards (the attached image). In 1-3 sentences, describe the STYLE to emulate when writing new on-brand cards: the copy patterns (hook, rhythm, length, diction, how the CTA reads) and the visual direction (mood, composition, imagery). Describe patterns to emulate through our own card templates — do NOT instruct a pixel-faithful copy of this exact layout, and do not invent facts. Call the exemplar_note tool with one concise note."""


def build_exemplar_system() -> str:
    return _EXEMPLAR_SYSTEM


def build_exemplar_user() -> str:
    return "Study the attached brand card and record a concise style note to emulate in future cards."


EXEMPLAR_NOTE_TOOL = {
    "name": "exemplar_note",
    "description": "Record a concise style note (copy + visual direction) to emulate from a past brand card.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "style_note": {
                "type": "string",
                "description": "1-3 sentences on the copy patterns and visual direction to emulate.",
            }
        },
        "required": ["style_note"],
    },
}
