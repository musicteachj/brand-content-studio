"""AI-draft fill for templates (Phase 5, optional path). A forced strict tool-use
call whose schema is built from THIS template's placeholder names, so the model
returns exactly one value per placeholder. Tone is secondary here — the value of
templates is consistent styling, not bespoke prose — so the prompt stays concise."""
from __future__ import annotations

from typing import Any

_FILL_SYSTEM = """You fill in the fields of a branded document template. You are given the template's field names and a short brief. Return concise, professional copy for each field by calling the provided tool. Keep each value short and appropriate to its field name; do not invent specific statistics or facts that aren't in the brief. Plain text only — no markdown."""


def build_fill_system() -> str:
    return _FILL_SYSTEM


def build_fill_user(brief: str, placeholders: list[str]) -> str:
    return "\n".join(
        [
            f'Brief: "{brief.strip()}"',
            "",
            "Fields to fill (call the fill_template tool with a value for each):",
            ", ".join(placeholders),
        ]
    )


def build_fill_user_from_content(content: str, placeholders: list[str]) -> str:
    return "\n".join(
        [
            "Source document content to map into the template's fields:",
            '"""',
            content.strip(),
            '"""',
            "",
            "Map the source content onto these fields (call the fill_template tool with a "
            "value for each). Condense to fit each field; leave a field empty if the source "
            "has nothing for it:",
            ", ".join(placeholders),
        ]
    )


def build_fill_tool(placeholders: list[str]) -> dict[str, Any]:
    """A strict tool whose properties are exactly this template's placeholders."""
    props = {
        name: {"type": "string", "description": f"Copy for the '{name}' field."}
        for name in placeholders
    }
    return {
        "name": "fill_template",
        "description": "Provide a value for each field of the document template.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": props,
            "required": list(placeholders),
        },
    }
