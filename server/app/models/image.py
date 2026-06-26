"""Image models — Unsplash search results (server-proxied) + upload response.

Attribution is normalized server-side and is non-optional on Unsplash results:
the picker and the card both render it (Unsplash license, ARCHITECTURE gotcha #4).
"""
from __future__ import annotations

from pydantic import BaseModel


class UnsplashAttribution(BaseModel):
    author: str
    author_url: str
    source_url: str


class UnsplashPhoto(BaseModel):
    id: str
    description: str | None = None
    thumb_url: str  # picker grid
    preview_url: str  # card render (regular size)
    width: int
    height: int
    color: str | None = None  # dominant color → placeholder while loading
    attribution: UnsplashAttribution
    download_location: str  # fired on selection (license requirement)


class UnsplashSearchResponse(BaseModel):
    query: str
    page: int
    total_pages: int
    results: list[UnsplashPhoto]


class ImageUploadResponse(BaseModel):
    source: str = "upload"
    storage_key: str
    url: str


class TrackDownloadRequest(BaseModel):
    download_location: str
