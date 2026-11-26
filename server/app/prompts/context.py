"""Shared assembly of the <brand_context> block handed to the model.

The chunk text and the source filename are untrusted — they come from uploaded
brand documents — so they are XML-escaped before interpolation. Without it, a
chunk containing `</source></brand_context>` could break out of the fence and
have its trailing text read by the model as top-level instructions (prompt
injection). The escaping is the structural defense; the `SECURITY:` clause in
each system prompt is the semantic one.
"""
from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from app.rag.vector_store import RetrievedChunk


def format_brand_context(chunks: list[RetrievedChunk]) -> str:
    """Render retrieved chunks as a <brand_context> block with untrusted values escaped."""
    if not chunks:
        return "<brand_context>(no brand material retrieved)</brand_context>"
    lines = ["<brand_context>"]
    for i, chunk in enumerate(chunks, start=1):
        meta = chunk.get("metadata") or {}
        source = str(meta.get("filename", "unknown"))
        kind = str(meta.get("asset_kind", "other"))
        # quoteattr adds the surrounding quotes and escapes "/</>/&; escape() does
        # the element text so `</source>` in a chunk can't close the fence early.
        lines.append(f"  <source id=\"{i}\" file={quoteattr(source)} kind={quoteattr(kind)}>")
        lines.append(escape(chunk["text"].strip()))
        lines.append("  </source>")
    lines.append("</brand_context>")
    return "\n".join(lines)
