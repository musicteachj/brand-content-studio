"""Auth + workspace-scoping dependencies."""

from bson import ObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_database
from app.models.user import UserInDB
from app.rag.vector_store import VectorStore
from app.services import retrieval_service
from app.services.auth_service import get_user_by_id
from app.utils.errors import NO_CONTEXT_COPY
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
    store: VectorStore, namespace: str, brief: str
) -> retrieval_service.RetrievalResult:
    """Retrieve brand context for a generate route's brief, or refuse with a 409 before
    anything is reserved or streamed: never generate with no context."""
    result = await retrieval_service.retrieve(store, namespace, brief, k=6)
    if not result.chunks:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=NO_CONTEXT_COPY)
    return result


def require_not_demo(current_user: UserInDB = Depends(get_current_user)) -> UserInDB:
    """Block destructive actions for the seeded demo user so visitors can't
    break the seeded Verdure corpus (DECISIONS #15)."""
    if current_user.is_demo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action is disabled in the demo. Sign in with your own account to modify workspaces.",
        )
    return current_user


def ledger_visitor_id(user: UserInDB) -> str | None:
    """Whose allowance an AI action is counted against in the dollar ledger, beside the
    shared daily and monthly budget. None for everyone today; demo sessions get their own
    ID (and a per-visitor cap) when they arrive."""
    _ = user
    return None
