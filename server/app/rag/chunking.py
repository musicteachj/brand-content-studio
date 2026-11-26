"""Text chunking. Standard prose uses RecursiveCharacterTextSplitter
(800/120, the only piece of LangChain we pull in — see DECISIONS #8). The
`posts` asset kind is split one-chunk-per-post on the `---` delimiter, because
whole exemplar posts are the highest-value retrieval target (ARCHITECTURE §4).
"""
from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
SEPARATORS = ["\n\n", "\n", ". ", " "]

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=SEPARATORS,
    keep_separator=True,
)


def chunk_text(text: str) -> list[str]:
    """Split prose into ~800-char chunks with 120-char overlap."""
    return [c.strip() for c in _splitter.split_text(text) if c.strip()]


def split_posts(text: str) -> list[str]:
    """One chunk per exemplar post. Posts are delimited by a line that is just
    `---`. A leading title/preamble block (before the first `---`) is dropped if
    it looks like a markdown heading."""
    raw_parts = [p.strip() for p in text.split("\n---\n")]
    # Also handle a file that starts/ends with the delimiter or uses "---" alone.
    posts: list[str] = []
    for part in raw_parts:
        part = part.strip().strip("-").strip()
        if not part:
            continue
        # Drop a pure-markdown preamble (heading + blockquote) with no post body.
        lines = [ln for ln in part.splitlines() if ln.strip()]
        if lines and all(ln.lstrip().startswith(("#", ">")) for ln in lines):
            continue
        posts.append(part)
    return posts
