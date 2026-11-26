"""Unsplash search proxy + download tracking.

Server-proxied so the access key never reaches the client (ARCHITECTURE gotcha #4).
Two license obligations are handled here:
  1. Attribution is normalized onto every result and is non-optional — the picker
     and the card both render "Photo by X on Unsplash".
  2. The download-tracking endpoint is fired when a photo is selected (not on
     search) — required by the Unsplash API guidelines.

UTM params are appended to author/source links per the attribution guidelines.

Search results are cached in process for an hour (at most 256 searches), keyed by the
case-folded query and the page: the key's hourly quota is shared by every visitor, and
the demo's visitors search for much the same things.
"""
from __future__ import annotations

import time
from collections import OrderedDict
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.models.image import (
    UnsplashAttribution,
    UnsplashPhoto,
    UnsplashSearchResponse,
)
from app.utils.errors import IMAGE_SEARCH_UNAVAILABLE_COPY

_API_BASE = "https://api.unsplash.com"
_UTM = "utm_source=Folio&utm_medium=referral"
_TIMEOUT = httpx.Timeout(10.0)
PER_PAGE = 24

SEARCH_CACHE_SECONDS = 3600
SEARCH_CACHE_MAX_ENTRIES = 256
# (casefolded query, page) -> (stored at, response); least recently used first.
_search_cache: OrderedDict[tuple[str, int], tuple[float, UnsplashSearchResponse]] = OrderedDict()


def clear_search_cache() -> None:
    _search_cache.clear()


def search_cache_size() -> int:
    return len(_search_cache)


def _cached(key: tuple[str, int]) -> UnsplashSearchResponse | None:
    hit = _search_cache.get(key)
    if hit is None:
        return None
    stored_at, response = hit
    if time.monotonic() - stored_at > SEARCH_CACHE_SECONDS:
        del _search_cache[key]
        return None
    _search_cache.move_to_end(key)
    return response


def _remember(key: tuple[str, int], response: UnsplashSearchResponse) -> None:
    _search_cache[key] = (time.monotonic(), response)
    _search_cache.move_to_end(key)
    while len(_search_cache) > SEARCH_CACHE_MAX_ENTRIES:
        _search_cache.popitem(last=False)


class UnsplashError(RuntimeError):
    """Raised when Unsplash is unconfigured, unreachable, unauthorized, or rate-limited.
    The route always answers with IMAGE_SEARCH_UNAVAILABLE_COPY; the text here is for
    the log."""


def _require_key() -> str:
    key = settings.unsplash_access_key.get_secret_value()
    if not key:
        raise UnsplashError(IMAGE_SEARCH_UNAVAILABLE_COPY)
    return key


def _with_utm(url: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{_UTM}"


def _normalize(photo: dict) -> UnsplashPhoto:
    user = photo.get("user") or {}
    urls = photo.get("urls") or {}
    links = photo.get("links") or {}
    user_links = user.get("links") or {}
    return UnsplashPhoto(
        id=photo["id"],
        description=photo.get("description") or photo.get("alt_description"),
        thumb_url=urls.get("small", urls.get("thumb", "")),
        preview_url=urls.get("regular", urls.get("full", "")),
        width=int(photo.get("width") or 0),
        height=int(photo.get("height") or 0),
        color=photo.get("color"),
        attribution=UnsplashAttribution(
            author=user.get("name") or "Unknown",
            author_url=_with_utm(user_links.get("html", "https://unsplash.com")),
            source_url=_with_utm(links.get("html", "https://unsplash.com")),
        ),
        download_location=links.get("download_location", ""),
    )


async def search(query: str, page: int = 1) -> UnsplashSearchResponse:
    page = max(1, page)
    cache_key = (query.casefold().strip(), page)
    cached = _cached(cache_key)
    if cached is not None:
        return cached.model_copy(update={"query": query})
    key = _require_key()
    params: dict[str, str | int] = {
        "query": query,
        "page": page,
        "per_page": PER_PAGE,
        "content_filter": "high",
        "orientation": "portrait",  # cards are 4:5 portrait
    }
    headers = {"Authorization": f"Client-ID {key}", "Accept-Version": "v1"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_API_BASE}/search/photos", params=params, headers=headers
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise UnsplashError(f"Unsplash search failed ({exc.response.status_code}).") from exc
    except httpx.HTTPError as exc:
        raise UnsplashError("Could not reach Unsplash.") from exc

    response = UnsplashSearchResponse(
        query=query,
        page=page,
        total_pages=int(data.get("total_pages") or 0),
        results=[_normalize(p) for p in data.get("results", [])],
    )
    _remember(cache_key, response)
    return response


async def track_download(download_location: str) -> None:
    """Fire the Unsplash download-tracking endpoint on selection (license
    requirement). The `download_location` URL already carries Unsplash's own
    signed params; we only append the Client-ID. Best-effort — failures here must
    not block the user's selection, so the caller swallows errors.

    SECURITY: `download_location` arrives from the client, so it is validated to
    be an `https://api.unsplash.com/...` URL before any request is made. Without
    this, the endpoint is an SSRF that also leaks the Client-ID header to any host
    the caller names."""
    if not download_location or not _is_unsplash_download_url(download_location):
        return
    key = _require_key()
    headers = {"Authorization": f"Client-ID {key}", "Accept-Version": "v1"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(download_location, headers=headers)
        resp.raise_for_status()


def _is_unsplash_download_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.hostname == "api.unsplash.com"
