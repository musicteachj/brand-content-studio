"""Exemplar steering (Phase 4c). Joins the per-exemplar style notes into a single
trusted instruction block appended to the generation system prompt — the same
seam as `voice_summary`. The notes are the owner's own derived brand guidance, so
they are instructions to follow (not untrusted retrieved data)."""
from __future__ import annotations


def build_exemplar_guidance(notes: list[str]) -> str | None:
    """A trusted 'examples to emulate' block, or None when there are no notes."""
    clean = [n.strip() for n in notes if n and n.strip()]
    if not clean:
        return None
    lines = [
        "On-brand examples to emulate (the brand's own past cards — match their "
        "style and patterns, but do not copy their exact words):"
    ]
    for i, note in enumerate(clean, start=1):
        lines.append(f"{i}. {note}")
    return "\n".join(lines)


def build_brand_context(workspace: dict) -> tuple[str, dict, str | None, str | None]:
    """Assemble a generation's brand inputs from a workspace dict: the vector
    namespace, the raw `brand_profile`, the voice summary, and the exemplar-steering
    guidance block. Shared by the four streamed-generation routes (ARCH-02); the
    document route ignores the exemplar guidance."""
    brand_profile = workspace.get("brand_profile") or {}
    return (
        workspace["vector_namespace"],
        brand_profile,
        brand_profile.get("voice_summary"),
        build_exemplar_guidance(
            [e.get("style_note", "") for e in (brand_profile.get("exemplars") or [])]
        ),
    )
