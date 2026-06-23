"""Health check — reports mongo + vector store status."""
from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_database
from app.rag.vector_store import get_vector_store

router = APIRouter()


@router.get("/health")
async def health_check(db: AsyncIOMotorDatabase = Depends(get_database)) -> dict:
    try:
        await db.command("ping")
        mongo_ok = True
    except Exception:
        mongo_ok = False

    try:
        vector_ok = await get_vector_store().health()
    except Exception:
        vector_ok = False

    return {
        "status": "ok" if (mongo_ok and vector_ok) else "degraded",
        "mongo": mongo_ok,
        "vector_store": vector_ok,
    }
