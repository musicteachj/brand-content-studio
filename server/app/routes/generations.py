"""Content history routes — list (with type filter), get one, delete."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_database
from app.models.generation import GenerationResponse
from app.services import generations_service
from app.utils.dependencies import get_workspace_or_404, require_not_demo

router = APIRouter()


@router.get("", response_model=list[GenerationResponse])
async def list_generations(
    type: str = Query("all", pattern="^(all|text|card)$"),
    workspace: dict = Depends(get_workspace_or_404),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    return await generations_service.list_generations(db, workspace["_id"], type)


@router.get("/{generation_id}", response_model=GenerationResponse)
async def get_generation(
    generation_id: str,
    workspace: dict = Depends(get_workspace_or_404),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    doc = await generations_service.get_generation(db, workspace["_id"], generation_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found")
    return generations_service.to_response(doc)


@router.delete("/{generation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_generation(
    generation_id: str,
    workspace: dict = Depends(get_workspace_or_404),
    _: object = Depends(require_not_demo),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    ok = await generations_service.delete_generation(db, workspace["_id"], generation_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found")
