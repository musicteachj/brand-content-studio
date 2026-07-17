"""Auth + workspace-scoping dependencies."""

from bson import ObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import settings
from app.database import get_database
from app.models.common import utcnow
from app.models.user import UserInDB
from app.services.auth_service import get_user_by_id
from app.utils.security import decode_access_token

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> UserInDB:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise credentials_exception
    user_id: str | None = payload.get("user_id")
    if user_id is None:
        raise credentials_exception
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    return user


async def get_workspace_or_404(
    workspace_id: str,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    """Resolve a workspace by id and enforce `owner_id == current_user`.

    Returns the raw Mongo doc (callers need `vector_namespace`, `brand_profile`,
    `ready_chunk_count`, …). A non-owner gets a 404 — we don't reveal existence.
    """
    try:
        oid = ObjectId(workspace_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        ) from None
    doc = await db.workspaces.find_one({"_id": oid})
    if not doc or str(doc.get("owner_id")) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return doc


def require_not_demo(current_user: UserInDB = Depends(get_current_user)) -> UserInDB:
    """Block destructive actions for the seeded demo user so visitors can't
    break the seeded Verdure corpus (DECISIONS #15)."""
    if current_user.is_demo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action is disabled in the demo. Sign in with your own account to modify workspaces.",
        )
    return current_user


async def enforce_demo_generation_quota(
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> None:
    """Cap the shared demo account's paid generations per UTC day (SEC-02). Per-IP
    rate limits don't bound aggregate demo spend across many visitors; this does.
    Non-demo users are unaffected."""
    if not current_user.is_demo:
        return
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    used = await db.generations.count_documents(
        {"owner_id": ObjectId(current_user.id), "created_at": {"$gte": start}}
    )
    if used >= settings.demo_daily_generation_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="The demo's daily generation limit has been reached — try again tomorrow.",
        )
