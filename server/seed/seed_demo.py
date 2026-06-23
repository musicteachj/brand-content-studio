"""Seed the demo user + an empty Verdure Materials workspace.

Run from the server/ directory:  python -m seed.seed_demo
(or `npm run seed` from the repo root). Idempotent. The Verdure corpus is
ingested in Phase 1a once the ingestion pipeline exists.
"""
import asyncio
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.utils.security import get_password_hash

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


async def main() -> None:
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.database_name]
    await db.users.create_index("email", unique=True)

    demo = await db.users.find_one({"is_demo": True})
    if demo:
        owner_id = demo["_id"]
        print(f"✓ demo user exists ({demo['email']})")
    else:
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
        owner_id = res.inserted_id
        print(f"+ created demo user ({settings.demo_email})")

    existing = await db.workspaces.find_one({"owner_id": owner_id, "slug": "verdure-materials"})
    if existing:
        print("✓ Verdure Materials workspace exists")
    else:
        now = datetime.now(timezone.utc)
        res = await db.workspaces.insert_one(
            {
                "owner_id": owner_id,
                "name": "Verdure Materials",
                "slug": "verdure-materials",
                "brand_profile": VERDURE_BRAND_PROFILE,
                "embedding_model": settings.embedding_model,
                "embedding_dim": settings.embedding_dim,
                "asset_count": 0,
                "ready_chunk_count": 0,
                "created_at": now,
                "updated_at": now,
            }
        )
        await db.workspaces.update_one(
            {"_id": res.inserted_id},
            {"$set": {"vector_namespace": str(res.inserted_id)}},
        )
        print("+ created empty Verdure Materials workspace")

    client.close()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
