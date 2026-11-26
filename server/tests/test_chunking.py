"""Chunking is deterministic and respects size/overlap; posts split one-per-post."""
from app.rag.chunking import CHUNK_OVERLAP, CHUNK_SIZE, chunk_text, split_posts
from app.rag.loaders import Section
from app.services.ingestion_service import build_chunks


def test_chunking_respects_size_overlap():
    # 400 uniquely-numbered tokens (~2000 chars), no paragraph breaks.
    text = " ".join(f"token{i}" for i in range(400))
    chunks = chunk_text(text)

    assert len(chunks) > 1, "long text should split into multiple chunks"
    # Each chunk stays within the configured size (small tolerance for separators).
    assert all(len(c) <= CHUNK_SIZE + 50 for c in chunks)

    # Consecutive chunks overlap (the splitter carries ~CHUNK_OVERLAP chars over).
    first_tokens = set(chunks[0].split())
    second_tokens = set(chunks[1].split())
    assert first_tokens & second_tokens, "consecutive chunks should share overlap tokens"
    assert CHUNK_OVERLAP > 0


def test_split_posts_one_chunk_per_post():
    text = "Post one body.\n\n#Tag1\n---\nPost two body.\n\n#Tag2\n---\nPost three.\n\n#Tag3"
    posts = split_posts(text)
    assert len(posts) == 3
    assert posts[0].startswith("Post one")
    assert posts[2].startswith("Post three")


def test_build_chunks_posts_metadata_and_ids():
    text = "Alpha post.\n---\nBeta post.\n---\nGamma post."
    chunks = build_chunks(
        workspace_namespace="ns",
        asset_id="aid",
        asset_kind="posts",
        filename="past-posts.md",
        sections=[Section(text=text)],
    )
    assert [c["id"] for c in chunks] == ["aid:0", "aid:1", "aid:2"]
    meta = chunks[0]["metadata"]
    assert meta["workspace_id"] == "ns"
    assert meta["asset_kind"] == "posts"
    assert meta["chunk_index"] == 0
    assert "page" not in meta  # markdown has no page numbers


def test_build_chunks_pdf_section_carries_page():
    chunks = build_chunks(
        workspace_namespace="ns",
        asset_id="aid",
        asset_kind="voice",
        filename="voice.pdf",
        sections=[Section(text="Some brand voice prose.", page=3)],
    )
    assert chunks[0]["metadata"]["page"] == 3
