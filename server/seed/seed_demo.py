"""Seed the demo user + the Verdure Materials workspace, with its brand corpus
pre-ingested (DECISIONS #15 — visitors hit the RAG "wow" instantly).

Run from the server/ directory:  python -m seed.seed_demo
(or `npm run seed` from the repo root). Idempotent: re-running won't duplicate
the user, workspace, or assets. Corpus ingestion needs OPENAI_API_KEY + a
running Chroma; if the key is missing the workspace is created empty and you can
re-run after adding the key.
"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.rag.loaders import load_sections
from app.rag.vector_store import get_vector_store
from app.services.ingestion_service import build_chunks
from app.services.storage_service import build_storage_key, get_storage
from app.utils.security import get_password_hash

CORPUS_DIR = Path(__file__).resolve().parent / "verdure_corpus"

# (filename, content_type, asset_kind). The voice guide is ingested as a PDF to
# exercise the pdfplumber path; the rest are markdown.
CORPUS = [
    ("voice-and-tone.pdf", "application/pdf", "voice"),
    ("content-pillars.md", "text/markdown", "pillars"),
    ("past-posts.md", "text/markdown", "posts"),
    ("personas.md", "text/markdown", "personas"),
    ("competitors.md", "text/markdown", "competitors"),
]

VERDURE_BRAND_PROFILE = {
    "colors": [
        {"name": "Forest", "hex": "#1C3A2E", "role": "primary"},
        {"name": "Cream", "hex": "#F4F1E9", "role": "neutral"},
        {"name": "Ochre", "hex": "#C98A3D", "role": "accent"},
    ],
    "accent_hex": "#1C3A2E",
    "fonts": {"heading": "DM Serif Display", "body": "Spectral", "mono": None},
    "logo": None,
    "voice_summary": (
        "Verdure is the grounded, data-first voice of low-carbon building materials — "
        "plain-spoken, evidence-led, and respectful of the professionals who specify and build."
    ),
}


async def _ensure_demo_user(db) -> ObjectId:
    demo = await db.users.find_one({"is_demo": True})
    if demo:
        print(f"✓ demo user exists ({demo['email']})")
        return demo["_id"]
    now = datetime.now(timezone.utc)
    res = await db.users.insert_one(
        {
            "email": settings.demo_email,
            "hashed_password": get_password_hash(settings.demo_password),
            "full_name": settings.demo_full_name,
            "is_active": True,
            "is_admin": False,
            "is_demo": True,
            "created_at": now,
            "updated_at": now,
        }
    )
    print(f"+ created demo user ({settings.demo_email})")
    return res.inserted_id


async def _ensure_workspace(db, owner_id: ObjectId) -> dict:
    existing = await db.workspaces.find_one({"owner_id": owner_id, "slug": "verdure-materials"})
    if existing:
        print("✓ Verdure Materials workspace exists")
        return existing
    now = datetime.now(timezone.utc)
    workspace_oid = ObjectId()
    doc = {
        "_id": workspace_oid,
        "owner_id": owner_id,
        "name": "Verdure Materials",
        "slug": "verdure-materials",
        "brand_profile": VERDURE_BRAND_PROFILE,
        "vector_namespace": str(workspace_oid),
        "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim,
        "asset_count": 0,
        "ready_chunk_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    await db.workspaces.insert_one(doc)
    print("+ created Verdure Materials workspace")
    return doc


async def _ingest_corpus(db, workspace: dict) -> None:
    if await db.assets.count_documents({"workspace_id": workspace["_id"]}) > 0:
        print("✓ corpus already ingested")
        return
    if not settings.openai_api_key:
        print("⚠ OPENAI_API_KEY not set — workspace created empty. Add the key and re-run to ingest.")
        return

    namespace = workspace["vector_namespace"]
    store = get_vector_store()
    storage = get_storage()
    total_chunks = 0
    asset_count = 0
    now = datetime.now(timezone.utc)

    for filename, content_type, kind in CORPUS:
        path = CORPUS_DIR / filename
        if not path.exists():
            print(f"⚠ missing corpus file {filename}; skipping")
            continue
        data = path.read_bytes()
        asset_oid = ObjectId()
        storage_key = build_storage_key(namespace, str(asset_oid), filename)
        await storage.save(storage_key, data)

        sections = load_sections(storage.local_path(storage_key), content_type)
        chunks = build_chunks(
            workspace_namespace=namespace,
            asset_id=str(asset_oid),
            asset_kind=kind,
            filename=filename,
            sections=sections,
        )
        count = await store.upsert_chunks(namespace, chunks)
        await db.assets.insert_one(
            {
                "_id": asset_oid,
                "workspace_id": workspace["_id"],
                "filename": filename,
                "content_type": content_type,
                "asset_kind": kind,
                "storage_key": storage_key,
                "size_bytes": len(data),
                "ingestion_status": "ready",
                "chunk_count": count,
                "error": None,
                "ingested_at": now,
                "created_at": now,
                "updated_at": now,
            }
        )
        total_chunks += count
        asset_count += 1
        print(f"  + {filename} → {count} chunks ({kind})")

    await db.workspaces.update_one(
        {"_id": workspace["_id"]},
        {"$set": {"asset_count": asset_count, "ready_chunk_count": total_chunks, "updated_at": now}},
    )
    print(f"+ ingested Verdure corpus: {total_chunks} chunks across {asset_count} assets")


async def main() -> None:
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.database_name]
    await db.users.create_index("email", unique=True)

    owner_id = await _ensure_demo_user(db)
    workspace = await _ensure_workspace(db, owner_id)
    await _ingest_corpus(db, workspace)

    client.close()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
