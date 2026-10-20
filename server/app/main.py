"""FastAPI application entrypoint."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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
from app.spa import mount_spa
from app.utils.ratelimit import limiter

logging.basicConfig(level=logging.INFO)


# The SPA's Content-Security-Policy (known-gaps plan, step 2; DECISIONS #36),
# tightened by a browser pass over every flow on the production build:
# - script-src: the bundle only. 'wasm-unsafe-eval' lets WebAssembly compile
#   (resvg rasterizes card PNGs, satori lays them out); no eval, no inline script.
# - style-src 'unsafe-inline': Radix dialogs inject a <style> element for scroll
#   locking. React style props go through the CSSOM and don't need it.
# - Card fonts come from jsDelivr (fetched as bytes, and loaded as FontFace URLs);
#   Unsplash photos are shown from, and fetched into data URLs from, its CDNs.
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' 'wasm-unsafe-eval'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob: https://images.unsplash.com https://plus.unsplash.com",
        "font-src 'self' data: https://cdn.jsdelivr.net",
        "connect-src 'self' https://cdn.jsdelivr.net https://images.unsplash.com https://plus.unsplash.com",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)

_CSP_HEADER = {
    "enforce": "Content-Security-Policy",
    "report-only": "Content-Security-Policy-Report-Only",
}

def api_docs_urls(environment: str) -> dict[str, str | None]:
    """FastAPI's Swagger UI, ReDoc, and OpenAPI schema are for local development.
    In production they'd hand anyone probing the public demo a map of every
    route, and nothing in the app uses them."""
    if environment == "production":
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}


def csp_exempt_paths(app: FastAPI) -> frozenset[str]:
    """FastAPI's own docs pages load Swagger UI / ReDoc from jsDelivr and start
    them with an inline script, so the SPA policy would leave them blank. They're
    the one exemption, read from the app itself, so it only exists where the docs
    do: in production `/docs` is just a client route serving the SPA, under its CSP."""
    paths = {app.docs_url, app.redoc_url}
    if app.docs_url:
        paths.add(app.swagger_ui_oauth2_redirect_url)
    return frozenset(p for p in paths if p)


class SecurityHeadersMiddleware:
    """Baseline hardening headers on every response, including the CSP.

    Pure ASGI (not @app.middleware('http') / BaseHTTPMiddleware): that wraps the
    response body and can buffer SSE, and generation is served over SSE. This
    only rewrites the response-start headers and leaves the streaming body
    untouched. The CSP goes on every response (not just the SPA's HTML), so a
    user-uploaded file opened directly can't run script either. `csp_mode`
    switches it to report-only or off with an env change and a restart, no code
    change.
    """

    def __init__(self, app: ASGIApp, csp_exempt: frozenset[str] = frozenset()) -> None:
        self.app = app
        self.csp_exempt = csp_exempt

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
                csp_header = _CSP_HEADER.get(settings.csp_mode)
                if csp_header and scope["path"] not in self.csp_exempt:
                    headers.setdefault(csp_header, CONTENT_SECURITY_POLICY)
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


_docs = api_docs_urls(settings.environment)
app = FastAPI(
    title="Brand Content Studio API",
    description="RAG-powered on-brand LinkedIn content generation.",
    version="0.0.0",
    lifespan=lifespan,
    docs_url=_docs["docs_url"],
    redoc_url=_docs["redoc_url"],
    openapi_url=_docs["openapi_url"],
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


app.add_middleware(SecurityHeadersMiddleware, csp_exempt=csp_exempt_paths(app))

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
    mount_spa(app, Path("dist"))  # last: its catch-all only sees unclaimed paths
