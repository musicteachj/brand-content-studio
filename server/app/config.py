"""Application settings (pydantic-settings). Loads from server/.env."""
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    environment: str = "development"
    cors_origins: List[str] = ["http://localhost:5173"]

    # MongoDB
    mongodb_url: str = "mongodb://localhost:27017"
    database_name: str = "brand_content"

    # JWT
    jwt_secret_key: str = "CHANGE-THIS-IN-PRODUCTION"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Seeded demo user ("Explore as demo")
    demo_email: str = "demo@folio.studio"
    demo_password: str = "demo-folio-2026"
    demo_full_name: str = "Demo User"

    # AI — generation (Anthropic)
    anthropic_api_key: str = ""
    ai_model: str = "claude-sonnet-4-6"

    # AI — embeddings (OpenAI)
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    # Vector store: "chroma" (dev) | "qdrant" (prod)
    vector_store_backend: str = "chroma"
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "brand-content-studio"

    # Storage: "local" (dev) | "s3" (prod)
    storage_backend: str = "local"
    storage_local_dir: str = "./storage"
    s3_bucket: str = ""

    # Documents (Phase 2) — optional brand-font TTFs for exact PDF font embedding.
    # Drop `<font-slug>.ttf` files here (e.g. dm-serif-display.ttf) to embed real
    # brand fonts in generated PDFs; missing fonts fall back to a serif/sans base
    # font. No runtime network fetch — keeps the request path SSRF-free.
    brand_fonts_dir: str = str(Path(__file__).resolve().parent / "assets" / "fonts")

    # Images
    unsplash_access_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
