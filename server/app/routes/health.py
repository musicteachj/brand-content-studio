"""Liveness and readiness.

- `GET /api/health/live`: the process is up and serving. It never touches a database,
  so a Mongo outage can't get a running container restarted or pulled from the load
  balancer (the image's HEALTHCHECK and the ALB target health check both probe this one).
- `GET /api/health`: readiness. Mongo answers a ping, the vector store answers, and,
  when the seed runs at startup, the seed succeeded. Each check gets about two seconds;
  any failure is a 503 with the same keys, so a deploy smoke test catches an instance
  that can't serve visitors (docs/DEPLOY.md).

Both stay under `/api`: the SPA's catch-all (spa.py) owns every other path."""
import asyncio
from collections.abc import Awaitable

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import settings
from app.database import get_database
from app.rag.vector_store import get_vector_store

router = APIRouter()

CHECK_TIMEOUT_S = 2.0


async def _passes(check: Awaitable[bool]) -> bool:
    try:
        return bool(await asyncio.wait_for(check, CHECK_TIMEOUT_S))
    except Exception:  # noqa: BLE001 (any failure, a timeout included, is "not ready")
        return False


async def _mongo_ok(db: AsyncIOMotorDatabase) -> bool:
    await db.command("ping")
    return True


async def _vector_store_ok() -> bool:
    return await get_vector_store().health()


def _seed_ok(request: Request) -> bool | None:
    """None when the seed doesn't run at startup (nothing to report)."""
    if not settings.seed_on_startup:
        return None
    report = getattr(request.app.state, "seed_report", None)
    return report is not None and report.ok


@router.get("/health/live")
async def liveness() -> dict:
    return {"status": "ok"}


@router.get("/health")
async def readiness(
    request: Request, db: AsyncIOMotorDatabase = Depends(get_database)
) -> JSONResponse:
    mongo_ok, vector_ok = await asyncio.gather(
        _passes(_mongo_ok(db)), _passes(_vector_store_ok())
    )
    seed_ok = _seed_ok(request)
    ready = mongo_ok and vector_ok and seed_ok is not False
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ok" if ready else "unavailable",
            "mongo": mongo_ok,
            "vector_store": vector_ok,
            "seed": seed_ok,
        },
    )
