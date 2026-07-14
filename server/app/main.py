"""FastAPI application entrypoint."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import close_mongo_connection, connect_to_mongo, ensure_indexes
from app.rag.vector_store import get_vector_store
from app.routes import (
    assets,
    auth,
    documents,
    generate,
    generations,
    health,
    images,
    templates,
    workspaces,
)

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    await ensure_indexes()
    get_vector_store()  # instantiate the configured backend (chroma/qdrant)
    yield
    await close_mongo_connection()


app = FastAPI(
    title="Brand Content Studio API",
    description="RAG-powered on-brand LinkedIn content generation.",
    version="0.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    """Baseline hardening headers on every response. Deliberately no Content-
    Security-Policy yet — an enforcing CSP needs a browser QA pass (the SPA uses
    inline styles + resvg WebAssembly), so it's a separate follow-up."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if settings.environment == "production":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(workspaces.router, prefix="/api/workspaces", tags=["workspaces"])
app.include_router(
    assets.router, prefix="/api/workspaces/{workspace_id}/assets", tags=["assets"]
)
app.include_router(
    templates.router, prefix="/api/workspaces/{workspace_id}/templates", tags=["templates"]
)
app.include_router(
    generate.router, prefix="/api/workspaces/{workspace_id}/generate", tags=["generate"]
)
app.include_router(
    documents.router, prefix="/api/workspaces/{workspace_id}/generate", tags=["documents"]
)
app.include_router(
    generations.router,
    prefix="/api/workspaces/{workspace_id}/generations",
    tags=["generations"],
)
app.include_router(
    documents.download_router,
    prefix="/api/workspaces/{workspace_id}/generations",
    tags=["documents"],
)
app.include_router(images.router, prefix="/api/images", tags=["images"])
app.include_router(
    images.ws_router,
    prefix="/api/workspaces/{workspace_id}/images",
    tags=["images"],
)


if settings.environment == "production":
    app.mount("/static", StaticFiles(directory="dist"), name="static")

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        return FileResponse("dist/index.html")
