"""MongoDB connection + index management (Motor)."""
import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings


class Database:
    client: Optional[AsyncIOMotorClient] = None


db = Database()


async def get_database() -> AsyncIOMotorDatabase:
    if not db.client:
        raise RuntimeError("MongoDB client is not initialized. Call connect_to_mongo() first.")
    return db.client[settings.database_name]


async def connect_to_mongo() -> None:
    db.client = AsyncIOMotorClient(settings.mongodb_url)
    await db.client.admin.command("ping")
    logging.info("Connected to MongoDB (%s)", settings.database_name)


async def close_mongo_connection() -> None:
    if db.client:
        db.client.close()
        logging.info("Disconnected from MongoDB")


async def ensure_indexes() -> None:
    """Idempotent index creation (see docs/DATA_MODEL.md)."""
    assert db.client is not None, "connect_to_mongo() must run before ensure_indexes()"
    database = db.client[settings.database_name]
    await database.users.create_index("email", unique=True)
    await database.workspaces.create_index("owner_id")
    await database.workspaces.create_index([("owner_id", 1), ("slug", 1)], unique=True)
    await database.assets.create_index("workspace_id")
    await database.assets.create_index([("workspace_id", 1), ("ingestion_status", 1)])
    await database.generations.create_index([("workspace_id", 1), ("created_at", -1)])
    await database.generations.create_index([("workspace_id", 1), ("type", 1)])
    logging.info("Mongo indexes ensured")
