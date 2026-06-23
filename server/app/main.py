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
from app.routes import auth, health

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
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])


if settings.environment == "production":
    app.mount("/static", StaticFiles(directory="dist"), name="static")

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        return FileResponse("dist/index.html")
