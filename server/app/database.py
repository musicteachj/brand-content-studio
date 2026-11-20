"""MongoDB connection + index management (Motor)."""
import contextlib
import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import OperationFailure

from app.config import settings


class Database:
    client: AsyncIOMotorClient | None = None


db = Database()


async def get_database() -> AsyncIOMotorDatabase:
    if not db.client:
        raise RuntimeError("MongoDB client is not initialized. Call connect_to_mongo() first.")
    return db.client[settings.database_name]


async def connect_to_mongo() -> None:
    db.client = AsyncIOMotorClient(settings.mongodb_url.get_secret_value())
    await db.client.admin.command("ping")
    logging.info("Connected to MongoDB (%s)", settings.database_name)


async def close_mongo_connection() -> None:
    if db.client:
        db.client.close()
        logging.info("Disconnected from MongoDB")


async def ensure_ledger_indexes(database: AsyncIOMotorDatabase) -> None:
    """Indexes for the AI dollar ledger: the sweeper and prune scan open calls by age,
    and the pacing sum reads one month of day documents."""
    await database.ai_spend_calls.create_index([("status", 1), ("created_at", 1)])
    await database.ai_spend_days.create_index("month")


async def ensure_indexes() -> None:
    """Idempotent index creation (see docs/DATA_MODEL.md)."""
    if db.client is None:
        raise RuntimeError("connect_to_mongo() must run before ensure_indexes()")
    database = db.client[settings.database_name]
    await database.users.create_index("email", unique=True)
    await database.workspaces.create_index("owner_id")
    await database.workspaces.create_index([("owner_id", 1), ("slug", 1)], unique=True)
    await database.assets.create_index("workspace_id")
    await database.assets.create_index([("workspace_id", 1), ("ingestion_status", 1)])
    await database.generations.create_index([("workspace_id", 1), ("created_at", -1)])
    await database.generations.create_index([("workspace_id", 1), ("type", 1)])
    # A visitor's History: their own session's work, newest first.
    await database.generations.create_index(
        [("workspace_id", 1), ("session_id", 1), ("created_at", -1)]
    )
    # The cleanup job finds expired visitor work by expiry (not a TTL index: the job
    # removes each generation's files before its record).
    await database.generations.create_index("expires_at")
    # One of each ready-made example per workspace: the seed finds them by workspace and
    # key. Per workspace, so a recreated demo workspace can hold its own examples while an
    # old one's are still there.
    await database.generations.create_index(
        [("workspace_id", 1), ("example_key", 1)],
        unique=True,
        partialFilterExpression={"example_key": {"$exists": True}},
    )
    # The first, global version of that index; drop it where it still exists.
    with contextlib.suppress(OperationFailure):
        await database.generations.drop_index("example_key_1")
    # Only the old quota count used this; drop it where it still exists.
    with contextlib.suppress(OperationFailure):
        await database.generations.drop_index("owner_id_1_created_at_-1")
    await database.templates.create_index("workspace_id")
    # Visitor sessions: the cleanup job finds expired ones by expiry. Not a TTL index:
    # the job removes a session's work and spend with it.
    await database.demo_sessions.create_index("expires_at")
    await ensure_ledger_indexes(database)
    logging.info("Mongo indexes ensured")
