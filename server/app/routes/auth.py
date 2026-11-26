"""Auth routes: login (closed in production), the visitor demo start, me. No public signup."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from slowapi.util import get_remote_address

from app.config import settings
from app.database import get_database
from app.models.user import DemoStartRequest, Token, UserInDB, UserLogin, UserResponse
from app.services.auth_service import authenticate_user, get_demo_user
from app.services.session_service import SESSION_TTL, create_session, end_session
from app.services.turnstile import TurnstileVerifier, Verdict, get_turnstile_verifier
from app.utils.dependencies import get_current_user
from app.utils.errors import DEMO_NOT_READY_COPY, BotCheckFailed, BotCheckUnavailable
from app.utils.ratelimit import AUTH_RATE_LIMIT, limiter
from app.utils.security import create_access_token

router = APIRouter()


def _token(claims: dict, expires: timedelta) -> Token:
    return Token(
        access_token=create_access_token(data=claims, expires_delta=expires),
        token_type="bearer",  # noqa: S106 — OAuth token type, not a password
        expires_in=int(expires.total_seconds()),
    )


def _demo_starts_per_hour() -> str:
    return f"{settings.demo_starts_per_hour}/hour"


def _demo_starts_per_day() -> str:
    return f"{settings.demo_starts_per_day}/day"


def require_password_login() -> None:
    """Password sign-in is for local development. In production the public demo is the
    only way in, so the route answers as if it did not exist. Read per request, so a
    test can switch the environment."""
    if settings.environment == "production":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


@router.post("/login", response_model=Token, dependencies=[Depends(require_password_login)])
@limiter.limit(AUTH_RATE_LIMIT)
async def login(
    request: Request, credentials: UserLogin, db: AsyncIOMotorDatabase = Depends(get_database)
):
    user_doc = await authenticate_user(db, credentials.email, credentials.password)
    # The demo user is reached only through the bot-checked demo start, which gives it a
    # visitor session. A password token for it would be refused at once (no session), so
    # the right password is answered exactly as a wrong one, after the same hash check.
    if not user_doc or user_doc.get("is_demo"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = {"user_id": str(user_doc["_id"]), "email": user_doc["email"]}
    return _token(claims, timedelta(minutes=settings.access_token_expire_minutes))


@router.post("/demo-login", response_model=Token)
@limiter.limit(AUTH_RATE_LIMIT)
@limiter.limit(_demo_starts_per_hour)
@limiter.limit(_demo_starts_per_day)
async def demo_login(
    request: Request,
    body: DemoStartRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    verifier: TurnstileVerifier = Depends(get_turnstile_verifier),
):
    """'Explore as demo': after the bot check and the per-IP start limits, a new 24-hour
    visitor session for the seeded demo user, its ID carried in the token as `sid`."""
    verdict = await verifier.verify(body.turnstile_token, get_remote_address(request))
    if verdict is Verdict.UNAVAILABLE:
        raise BotCheckUnavailable()
    if verdict is not Verdict.PASSED:
        raise BotCheckFailed()
    user_doc = await get_demo_user(db)
    if not user_doc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=DEMO_NOT_READY_COPY)
    session = await create_session(db, user_id=user_doc["_id"])
    claims = {"user_id": str(user_doc["_id"]), "email": user_doc["email"], "sid": session["_id"]}
    return _token(claims, SESSION_TTL)


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


@router.post("/end-demo", status_code=status.HTTP_204_NO_CONTENT)
async def end_demo(
    current_user: UserInDB = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_database)
) -> Response:
    """'End demo': the visitor's session expires now, so the token stops working at once
    instead of lingering for 24 hours. Anyone else: nothing to end."""
    if current_user.is_demo and current_user.session_id:
        await end_session(db, current_user.session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
