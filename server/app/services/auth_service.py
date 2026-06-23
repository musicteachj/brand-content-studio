"""User lookup + authentication (mirrors EMS pattern)."""
from typing import Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.user import UserInDB
from app.utils.security import verify_password


async def get_user_by_email(db: AsyncIOMotorDatabase, email: str) -> Optional[UserInDB]:
    doc = await db.users.find_one({"email": email})
    return UserInDB(**doc) if doc else None


async def get_user_by_id(db: AsyncIOMotorDatabase, user_id: str) -> Optional[UserInDB]:
    try:
        doc = await db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None
    return UserInDB(**doc) if doc else None


async def get_demo_user(db: AsyncIOMotorDatabase) -> Optional[dict]:
    """Raw demo user doc (includes _id) for the demo-login bypass."""
    return await db.users.find_one({"is_demo": True})


async def authenticate_user(
    db: AsyncIOMotorDatabase, email: str, password: str
) -> Optional[dict]:
    doc = await db.users.find_one({"email": email})
    if not doc or not verify_password(password, doc["hashed_password"]) or not doc.get("is_active", True):
        return None
    return doc
