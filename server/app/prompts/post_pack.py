"""Prompt construction for the "LinkedIn Post" objective (Phase 3).

A post_pack is built in two coherent steps from ONE retrieval:
  1. CAPTION — reuse `prompts/text_post.py` to stream the full LinkedIn post caption.
  2. DISTILL — take that finished caption and distill the matching **card** (the
     visual hook) via a forced tool-use call, reusing `image_card.CARD_FIELDS_TOOL`.
     The card is the post's hook, not a copy of the caption — so this prompt asks
     the model to compress, not preserve wording.

The caption is the trusted source here (it was just generated under the brand
context), so no <brand_context> block is needed in the distill step — but the
model is still told not to invent facts beyond the caption.
"""
from __future__ import annotations

from app.models.generation import CardTemplate

# Mirror the card archetypes' shape so the distilled copy fits the layout it will
# be poured into (kept in sync with prompts/image_card.py).
_TEMPLATE_SHAPE = {
    CardTemplate.photo_led: (
        "a short eyebrow, a punchy headline (≤8 words), one tight supporting line, "
        "and a short CTA — the image carries the mood"
    ),
    CardTemplate.statement: (
        "a short eyebrow, a bold multi-line headline (the hero, ≤14 words), a compact "
        "one- or two-sentence body, and a CTA"
    ),
    CardTemplate.quote: (
        "a single quotable line as the headline (≤18 words), a short eyebrow, an "
        "optional one-line body, and a soft CTA"
    ),
}

_DISTILL_SYSTEM = """You turn a finished LinkedIn post into the matching social CARD by calling the provided tool. The card is the post's visual HOOK — the single strongest idea, compressed to a few words — not a re-statement of the whole post.

Rules:
- Distill, don't copy: pull the sharpest hook from the post into the headline; keep the brand's voice.
- Stay faithful: use only facts and claims already present in the post. Do not invent statistics, names, or facts.
- Plain text only: no arrows, emoji, or symbol characters — the card renders in a serif display font with no glyphs for them. Standard punctuation is fine.
- Then suggest concrete, literal image search keywords (nouns and scenes a stock-photo search understands), matching the post's subject."""


def build_distill_system() -> str:
    return _DISTILL_SYSTEM


def build_distill_user(brief: str, template: CardTemplate, caption: str) -> str:
    shape = _TEMPLATE_SHAPE.get(template, _TEMPLATE_SHAPE[CardTemplate.photo_led])
    return "\n".join(
        [
            f"Card template: {template.value} — {shape}.",
            f'Original brief: "{brief.strip()}"',
            "",
            "Finished LinkedIn post to distill into a card (compress to the hook; keep the voice):",
            "<post>",
            caption.strip(),
            "</post>",
            "",
            "Call the card_fields tool with the distilled card fields and suggested image keywords.",
        ]
    )
