"""Workspace CRUD routes. All workspace-scoped sub-routers (assets, generate,
generations) hang off `/workspaces/{workspace_id}` and go through
`get_workspace_or_404` for ownership."""
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_database
from app.models.user import UserInDB
from app.models.workspace import WorkspaceCreate, WorkspaceResponse, WorkspaceUpdate
from app.rag.vector_store import get_vector_store
from app.services import workspace_service
from app.utils.dependencies import get_current_user, get_workspace_or_404, require_not_demo

router = APIRouter()


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    return await workspace_service.list_workspaces(db, current_user.id)


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceCreate,
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    return await workspace_service.create_workspace(db, current_user.id, payload)


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace: dict = Depends(get_workspace_or_404),
):
    from app.models.common import serialize_doc

    return WorkspaceResponse(**serialize_doc(workspace))


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    payload: WorkspaceUpdate,
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    updated = await workspace_service.update_workspace(
        db, str(workspace["_id"]), current_user.id, payload
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return updated


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace: dict = Depends(get_workspace_or_404),
    current_user: UserInDB = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    namespace = workspace["vector_namespace"]
    await workspace_service.delete_workspace(db, str(workspace["_id"]), current_user.id)
    await get_vector_store().delete_workspace(namespace)
