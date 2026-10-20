"""Unsplash proxy: attribution is normalized onto every result (and UTM-tagged),
and the access key never appears in the normalized output. httpx is mocked so the
test makes no network call (and needs no real key)."""
import httpx
import pytest
from pydantic import SecretStr

from app.config import settings
from app.services import unsplash_service

_SAMPLE = {
    "total_pages": 3,
    "results": [
        {
            "id": "abc123",
            "description": "Hempcrete wall",
            "width": 4000,
            "height": 5000,
            "color": "#1c3a2e",
            "urls": {"small": "https://img/small.jpg", "regular": "https://img/regular.jpg"},
            "links": {
                "html": "https://unsplash.com/photos/abc123",
                "download_location": "https://api.unsplash.com/photos/abc123/download?ixid=xyz",
            },
            "user": {
                "name": "Jane Mason",
                "links": {"html": "https://unsplash.com/@janemason"},
            },
        }
    ],
}


@pytest.mark.asyncio
async def test_unsplash_search_normalizes_attribution(monkeypatch):
    monkeypatch.setattr(settings, "unsplash_access_key", SecretStr("test-key"))
    captured: dict = {}

    class _Resp:
        def raise_for_status(self) -> None:  # noqa: D401
            return None

        def json(self) -> dict:
            return _SAMPLE

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None, headers=None):
            captured["url"] = url
            captured["params"] = params
            captured["headers"] = headers
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    out = await unsplash_service.search("hempcrete", page=1)

    assert out.total_pages == 3
    assert len(out.results) == 1
    photo = out.results[0]
    # Attribution is present and complete (non-optional on the model).
    assert photo.attribution.author == "Jane Mason"
    assert "janemason" in photo.attribution.author_url
    assert "abc123" in photo.attribution.source_url
    # UTM referral params are appended per the Unsplash guidelines.
    assert "utm_source=Brand+Content+Studio" in photo.attribution.author_url
    assert "utm_source=Brand+Content+Studio" in photo.attribution.source_url
    # Download-tracking location is preserved for the on-selection ping.
    assert photo.download_location.startswith("https://api.unsplash.com/photos/abc123/download")
    # The key travels only in the request header, never in the normalized output.
    assert captured["headers"]["Authorization"] == "Client-ID test-key"
    assert "test-key" not in photo.model_dump_json()


@pytest.mark.asyncio
async def test_unsplash_search_without_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "unsplash_access_key", SecretStr(""))
    with pytest.raises(unsplash_service.UnsplashError):
        await unsplash_service.search("hempcrete")


@pytest.mark.asyncio
async def test_track_download_rejects_non_unsplash_url(monkeypatch):
    """SSRF guard: a client-supplied download_location that is not an
    api.unsplash.com URL must never be fetched (and never leak the key header)."""
    monkeypatch.setattr(settings, "unsplash_access_key", SecretStr("test-key"))
    called = {"get": False}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            called["get"] = True
            raise AssertionError("must not fetch a non-Unsplash URL")

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    for bad in [
        "http://169.254.169.254/latest/meta-data/",
        "https://evil.example.com/api.unsplash.com",
        "https://api.unsplash.com.evil.com/x",
        "ftp://api.unsplash.com/x",
        "",
    ]:
        await unsplash_service.track_download(bad)  # no-op, no request
    assert called["get"] is False


@pytest.mark.asyncio
async def test_track_download_allows_unsplash_url(monkeypatch):
    monkeypatch.setattr(settings, "unsplash_access_key", SecretStr("test-key"))
    seen: dict = {}

    class _Resp:
        def raise_for_status(self) -> None:
            return None

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            seen["url"] = url
            seen["headers"] = headers
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    await unsplash_service.track_download("https://api.unsplash.com/photos/abc/download?ixid=z")
    assert seen["url"].startswith("https://api.unsplash.com/")
    assert seen["headers"]["Authorization"] == "Client-ID test-key"
