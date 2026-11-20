"""The public examples: the four ready-made generations the seed writes into the demo
workspace (`is_example`), readable without signing in.

- `GET /api/examples`: the demo workspace's name, a slice of its brand profile, and the
  examples in display order. Cached in process for 60 s and by browsers and proxies for
  as long (`Cache-Control: public, max-age=60`). Nothing seeded is an empty list, never
  an error.
- `GET /api/examples/{generation_id}/download/{fmt}`: an example document's file. Only
  example documents qualify, and the storage key is rebuilt server-side, never read from
  the record; anything else is a 404.

NOTE: no `from __future__ import annotations` here: slowapi's @limiter.limit wrapper
can't resolve string annotations (see routes/generate.py)."""
import logging
import time

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError
from pymongo.errors import PyMongoError

from app.database import get_database
from app.models.common import BrandProfile
from app.models.examples import ExampleBrand, ExamplesResponse
from app.models.generation import EXAMPLE_KEYS, GenerationResponse
from app.routes.documents import DOC_MEDIA
from app.services import generations_service
from app.services.storage_service import build_document_key, get_storage, safe_filename
from app.utils.ratelimit import limiter

router = APIRouter()
logger = logging.getLogger(__name__)

EXAMPLES_RATE_LIMIT = "60/minute"
CACHE_SECONDS = 60
CACHE_CONTROL = f"public, max-age={CACHE_SECONDS}"
# The seeded demo workspace (seed/seed_demo.py).
DEMO_WORKSPACE_SLUG = "verdure-materials"

_cache: tuple[float, ExamplesResponse] | None = None


def clear_examples_cache() -> None:
    global _cache
    _cache = None


async def _demo_workspace(db: AsyncIOMotorDatabase) -> dict | None:
    demo = await db.users.find_one({"is_demo": True}, projection={"_id": 1})
    if demo is None:
        return None
    workspace: dict | None = await db.workspaces.find_one(
        {"owner_id": demo["_id"], "slug": DEMO_WORKSPACE_SLUG}
    )
    return workspace


async def _load(db: AsyncIOMotorDatabase) -> ExamplesResponse:
    workspace = await _demo_workspace(db)
    if workspace is None:
        return ExamplesResponse()
    order = {key: i for i, key in enumerate(EXAMPLE_KEYS)}
    docs = [d async for d in db.generations.find({"workspace_id": workspace["_id"], "is_example": True})]
    docs.sort(key=lambda d: (order.get(d.get("example_key"), len(order)), str(d["_id"])))
    items: list[GenerationResponse] = []
    for doc in docs:
        try:
            items.append(generations_service.to_response(doc))
        except ValidationError:
            logger.warning("Skipping example %s: it does not validate", doc.get("_id"))
    profile = BrandProfile(**(workspace.get("brand_profile") or {}))
    return ExamplesResponse(
        workspace_name=workspace.get("name") or "",
        brand=ExampleBrand(
            colors=profile.colors,
            fonts=profile.fonts,
            accent_hex=profile.accent_hex,
            voice_summary=profile.voice_summary,
        ),
        items=items,
    )


@router.get("", response_model=ExamplesResponse)
@limiter.limit(EXAMPLES_RATE_LIMIT)
async def list_examples(
    request: Request,
    response: Response,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    global _cache
    response.headers["Cache-Control"] = CACHE_CONTROL
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < CACHE_SECONDS:
        return _cache[1]
    try:
        result = await _load(db)
    except (PyMongoError, ValidationError):
        logger.exception("Could not load the examples")
        response.headers["Cache-Control"] = "no-store"
        return ExamplesResponse()
    _cache = (now, result)
    return result


@router.get("/{generation_id}/download/{fmt}")
@limiter.limit(EXAMPLES_RATE_LIMIT)
async def download_example(
    request: Request,
    generation_id: str,
    fmt: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    not_found = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Example not found")
    if fmt not in DOC_MEDIA:
        raise not_found
    try:
        oid = ObjectId(generation_id)
    except (InvalidId, TypeError):
        raise not_found from None
    doc = await db.generations.find_one({"_id": oid, "is_example": True, "type": "document"})
    if doc is None or fmt not in ((doc.get("output") or {}).get("formats") or {}):
        raise not_found
    key = build_document_key(str(doc["workspace_id"]), str(oid), fmt)
    try:
        data = await get_storage().read(key)
    except (FileNotFoundError, ValueError):
        raise not_found from None
    archetype = (doc.get("output") or {}).get("document", {}).get("archetype") or "document"
    filename = safe_filename(f"{archetype}.{fmt}")
    return Response(
        content=data,
        media_type=DOC_MEDIA[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
