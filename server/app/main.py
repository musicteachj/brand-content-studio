"""FastAPI application entrypoint."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings
from app.utils.ratelimit import limiter
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


class SecurityHeadersMiddleware:
    """Baseline hardening headers on every response.

    Pure ASGI (not @app.middleware('http') / BaseHTTPMiddleware): that wraps the
    response body and can buffer SSE, and generation is served over SSE — this
    only rewrites the response-start headers and leaves the streaming body
    untouched. No enforcing Content-Security-Policy yet: the SPA uses inline
    styles + resvg WebAssembly, so a CSP needs its own browser-QA'd pass.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                if settings.environment == "production":
                    headers.setdefault(
                        "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
                    )
            await send(message)

        await self.app(scope, receive, send_with_headers)


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

# Rate limiting (SEC-02): per-route @limiter.limit decorators read the limiter off
# app.state; the handler turns an exceeded limit into a 429.
app.state.limiter = limiter
# slowapi's handler is typed for RateLimitExceeded; Starlette wants Exception.
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.add_middleware(SecurityHeadersMiddleware)

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
