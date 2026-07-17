"""User + auth models. Single owner + a seeded demo user (no public signup)."""
from datetime import datetime

from pydantic import BaseModel, EmailStr


class User(BaseModel):
    email: EmailStr
    hashed_password: str
    full_name: str
    is_active: bool = True
    is_admin: bool = False
    is_demo: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UserInDB(User):
    id: str = ""  # str(_id), always populated by the auth service (_to_user)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str | None = None
    email: EmailStr
    full_name: str
    is_active: bool
    is_admin: bool
    is_demo: bool = False
    created_at: datetime | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 — OAuth token type, not a password
    expires_in: int  # seconds


class TokenData(BaseModel):
    email: str | None = None
    user_id: str | None = None
