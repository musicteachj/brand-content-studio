"""Auth routes: login, demo-login (bypass), me. No public signup."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import settings
from app.database import get_database
from app.models.user import Token, UserInDB, UserLogin, UserResponse
from app.services.auth_service import authenticate_user, get_demo_user
from app.utils.dependencies import get_current_user
from app.utils.security import create_access_token

router = APIRouter()


def _issue_token(user_doc: dict) -> Token:
    expires = timedelta(minutes=settings.access_token_expire_minutes)
    token = create_access_token(
        data={"user_id": str(user_doc["_id"]), "email": user_doc["email"]},
        expires_delta=expires,
    )
    return Token(
        access_token=token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/login", response_model=Token)
async def login(credentials: UserLogin, db: AsyncIOMotorDatabase = Depends(get_database)):
    user_doc = await authenticate_user(db, credentials.email, credentials.password)
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _issue_token(user_doc)


@router.post("/demo-login", response_model=Token)
async def demo_login(db: AsyncIOMotorDatabase = Depends(get_database)):
    """'Explore as demo' — issues a token for the seeded demo user, no credentials."""
    user_doc = await get_demo_user(db)
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo user not seeded. Run `npm run seed`.",
        )
    return _issue_token(user_doc)


@router.get("/me", response_model=UserResponse)
async def me(current_user: UserInDB = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_database)):
    doc = await db.users.find_one({"email": current_user.email})
    return UserResponse(
        id=str(doc["_id"]) if doc else None,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        is_admin=current_user.is_admin,
        is_demo=current_user.is_demo,
        created_at=current_user.created_at,
    )
