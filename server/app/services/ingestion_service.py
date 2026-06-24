"""Ingestion pipeline: parse → chunk → embed → upsert → mark ready.

Runs as a FastAPI BackgroundTask (DECISIONS — no task queue at portfolio
scale). The chunk-building step (`build_chunks`) is a pure function so it can be
unit-tested deterministically without a vector store or network."""
from __future__ import annotations

import logging

from bson import ObjectId

from app.database import get_database
from app.rag.chunking import chunk_text, split_posts
from app.rag.loaders import Section, load_sections
from app.rag.vector_store import Chunk, get_vector_store
from app.services import asset_service
from app.services.storage_service import get_storage

logger = logging.getLogger(__name__)

POSTS_KIND = "posts"


def build_chunks(
    *,
    workspace_namespace: str,
    asset_id: str,
    asset_kind: str,
    filename: str,
    sections: list[Section],
) -> list[Chunk]:
    """Turn parsed sections into vector-store chunks. `posts` are split one per
    exemplar post; everything else uses the 800/120 recursive splitter. Page
    numbers (PDFs) ride along in metadata for the debug panel."""
    chunks: list[Chunk] = []
    index = 0

    def _add(text: str, page: int | None) -> None:
        nonlocal index
        metadata: dict = {
            "workspace_id": workspace_namespace,
            "asset_id": asset_id,
            "filename": filename,
            "asset_kind": asset_kind,
            "chunk_index": index,
        }
        if page is not None:
            metadata["page"] = page
        chunks.append({"id": f"{asset_id}:{index}", "text": text, "metadata": metadata})
        index += 1

    if asset_kind == POSTS_KIND:
        combined = "\n---\n".join(s.text for s in sections)
        for post in split_posts(combined):
            _add(post, None)
    else:
        for section in sections:
            for piece in chunk_text(section.text):
                _add(piece, section.page)

    return chunks


async def ingest_asset(asset_id: str, workspace_namespace: str) -> None:
    """Background entrypoint. Reads the raw file, builds chunks, embeds + upserts
    them, then flips the asset to ready (or error)."""
    db = await get_database()
    asset_oid = ObjectId(asset_id)
    asset = await db.assets.find_one({"_id": asset_oid})
    if not asset:
        logger.warning("ingest_asset: asset %s vanished before ingestion", asset_id)
        return

    try:
        storage = get_storage()
        path = storage.local_path(asset["storage_key"])
        sections = load_sections(path, asset["content_type"])
        chunks = build_chunks(
            workspace_namespace=workspace_namespace,
            asset_id=asset_id,
            asset_kind=asset["asset_kind"],
            filename=asset["filename"],
            sections=sections,
        )
        if not chunks:
            await asset_service.mark_error(db, asset_oid, "No extractable text found in file.")
            return
        count = await get_vector_store().upsert_chunks(workspace_namespace, chunks)
        marked = await asset_service.mark_ready(db, asset_oid, count)
        if marked is None:
            # Asset was deleted while we were ingesting — drop the orphan vectors
            # so they can't leak into retrieval with no backing asset record.
            await get_vector_store().delete_asset(workspace_namespace, asset_id)
            logger.info("asset %s deleted mid-ingest; dropped %d orphan chunks", asset_id, count)
            return
        logger.info("ingested asset %s → %d chunks", asset_id, count)
    except Exception as exc:  # noqa: BLE001 — surface any failure as asset error state
        logger.exception("ingestion failed for asset %s", asset_id)
        await asset_service.mark_error(db, asset_oid, str(exc))
