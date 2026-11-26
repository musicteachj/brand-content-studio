"""Auth + workspace-scoping dependencies."""

from bson import ObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_database
from app.models.user import UserInDB
from app.rag.vector_store import VectorStore
from app.services import retrieval_service
from app.services.ai_meter import embedding_line, reserve_action
from app.services.auth_service import get_user_by_id
from app.services.session_service import get_active_session
from app.utils.errors import NO_CONTEXT_COPY, DemoEnded
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
    if user.is_demo:
        # A visitor's token is good only while its own session is live: a token from
        # before sessions, an expired session, or one the cleanup removed is a plain
        # "demo ended", which the client turns into a sign-out and a fresh start.
        sid = payload.get("sid")
        if not isinstance(sid, str) or not sid:
            raise DemoEnded()
        session = await get_active_session(db, sid)
        if session is None or str(session.get("user_id")) != user.id:
            raise DemoEnded()
        user.session_id = sid
        user.session_expires_at = session["expires_at"]
    return user


async def get_workspace_or_404(
    workspace_id: str,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    """Resolve a workspace by id and enforce `owner_id == current_user`.

    Returns the raw Mongo doc (callers need `vector_namespace`, `brand_profile`,
    `ready_chunk_count`, …). A non-owner gets a 404; we don't reveal existence.
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


def ensure_ready_corpus(workspace: dict) -> None:
    """Block generation on an empty/thin corpus BEFORE the model is called
    (ARCHITECTURE gotcha #10). Called at the top of every /generate route body: a
    plain guard (not a dependency) so it runs after the rate-limit dependency
    (preserving its precedence) and stays a real HTTP 409, which is the client's
    non-stream error path (never an in-stream frame)."""
    if int(workspace.get("ready_chunk_count", 0)) <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This workspace has no ingested brand assets yet. Ingest assets first.",
        )


async def retrieve_context_or_409(
    store: VectorStore,
    namespace: str,
    brief: str,
    *,
    db: AsyncIOMotorDatabase,
    visitor_id: str | None,
) -> retrieval_service.RetrievalResult:
    """Retrieve brand context for a generate route's brief, or refuse with a 409 before
    the model calls are reserved or anything is streamed: never generate with no context.

    The brief's embedding is reserved and settled in its own ledger action first (a budget
    refusal is a plain 429 here, before any OpenAI call)."""
    retrieval = await reserve_action(
        db, [embedding_line("retrieval", [brief])], visitor_id=visitor_id
    )
    async with retrieval:
        result = await retrieval_service.retrieve(store, namespace, brief, k=6, line=retrieval.lines[0])
    if not result.chunks:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=NO_CONTEXT_COPY)
    return result


def require_not_demo(current_user: UserInDB = Depends(get_current_user)) -> UserInDB:
    """Block destructive actions for the seeded demo user so visitors can't
    break the seeded Verdure corpus (DECISIONS #15)."""
    if current_user.is_demo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This part of the demo is read-only, so the sample brand stays the same for every visitor.",
        )
    return current_user


def history_scope(user: UserInDB) -> str | None:
    """Whose generations a user may reach in the workspace: a demo visitor's own session
    (plus the ready-made examples), or None for the owner, who sees the whole workspace.
    A demo user without a session fails closed (`get_current_user` never lets one through)."""
    if not user.is_demo:
        return None
    if not user.session_id:
        raise DemoEnded()
    return user.session_id


def ledger_visitor_id(user: UserInDB) -> str | None:
    """Whose allowance an AI action is counted against in the dollar ledger, beside the
    shared daily and monthly budget: a demo visitor's session ID (each session has its own
    cap), or None for the owner."""
    return user.session_id if user.is_demo else None
