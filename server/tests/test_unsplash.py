"""Unsplash proxy: attribution is normalized onto every result (and UTM-tagged),
and the access key never appears in the normalized output. httpx is mocked so the
test makes no network call (and needs no real key)."""
import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.config import settings
from app.main import app
from app.models.image import UnsplashSearchResponse
from app.models.user import UserInDB
from app.services import unsplash_service
from app.utils.dependencies import get_current_user
from app.utils.errors import IMAGE_SEARCH_UNAVAILABLE_COPY, RATE_LIMITED_COPY
from app.utils.ratelimit import RATE_LIMIT_UNSPLASH


@pytest.fixture(autouse=True)
def _fresh_search_cache():
    unsplash_service.clear_search_cache()
    yield
    unsplash_service.clear_search_cache()


@pytest.fixture
def signed_in():
    app.dependency_overrides[get_current_user] = lambda: UserInDB(
        id="65f000000000000000000001", email="o@example.com", hashed_password="x", full_name="O"
    )
    yield
    app.dependency_overrides.pop(get_current_user, None)

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


def _counting_client(calls: list[dict]):
    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return _SAMPLE

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None, headers=None):
            calls.append(params or {})
            return _Resp()

    return _Client


async def test_search_results_are_cached(monkeypatch):
    """The same search (case and outer spaces aside) within the hour is one upstream call;
    another page is its own entry."""
    monkeypatch.setattr(settings, "unsplash_access_key", SecretStr("test-key"))
    calls: list[dict] = []
    monkeypatch.setattr(httpx, "AsyncClient", _counting_client(calls))

    first = await unsplash_service.search("Hempcrete", page=1)
    second = await unsplash_service.search("  hempcrete ", page=1)
    assert len(calls) == 1
    assert second.results == first.results
    assert second.query == "  hempcrete "

    await unsplash_service.search("hempcrete", page=2)
    assert len(calls) == 2


async def test_cached_search_results_expire_after_an_hour(monkeypatch):
    monkeypatch.setattr(settings, "unsplash_access_key", SecretStr("test-key"))
    calls: list[dict] = []
    monkeypatch.setattr(httpx, "AsyncClient", _counting_client(calls))
    now = [1000.0]
    monkeypatch.setattr(unsplash_service.time, "monotonic", lambda: now[0])

    await unsplash_service.search("hempcrete")
    now[0] += 3599
    await unsplash_service.search("hempcrete")
    assert len(calls) == 1
    now[0] += 2
    await unsplash_service.search("hempcrete")
    assert len(calls) == 2


async def test_the_search_cache_keeps_at_most_256_entries(monkeypatch):
    monkeypatch.setattr(settings, "unsplash_access_key", SecretStr("test-key"))
    calls: list[dict] = []
    monkeypatch.setattr(httpx, "AsyncClient", _counting_client(calls))

    for i in range(257):
        await unsplash_service.search(f"query {i}")
    assert unsplash_service.search_cache_size() == 256
    await unsplash_service.search("query 0")  # the oldest entry was dropped
    assert len(calls) == 258
    await unsplash_service.search("query 256")  # the newest is still there
    assert len(calls) == 258


async def test_search_is_limited_per_ip(enabled_limiter, signed_in, monkeypatch):
    async def fake_search(query: str, page: int = 1) -> UnsplashSearchResponse:
        return UnsplashSearchResponse(query=query, page=page, total_pages=0, results=[])

    monkeypatch.setattr(unsplash_service, "search", fake_search)
    per_min = int(RATE_LIMIT_UNSPLASH.split("/")[0])
    assert per_min == 20
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        statuses = [
            (await ac.get("/api/images/unsplash/search", params={"q": "wall"})).status_code
            for _ in range(per_min)
        ]
        over = await ac.get("/api/images/unsplash/search", params={"q": "wall"})
    assert set(statuses) == {200}
    assert over.status_code == 429
    assert over.json() == {"detail": RATE_LIMITED_COPY, "code": "rate_limited"}


async def test_track_is_limited_per_ip(enabled_limiter, signed_in, monkeypatch):
    async def fake_track(download_location: str) -> None:
        return None

    monkeypatch.setattr(unsplash_service, "track_download", fake_track)
    per_min = int(RATE_LIMIT_UNSPLASH.split("/")[0])
    body = {"download_location": "https://api.unsplash.com/photos/abc/download"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        statuses = [
            (await ac.post("/api/images/unsplash/track", json=body)).status_code
            for _ in range(per_min + 1)
        ]
    assert statuses[:-1] == [204] * per_min
    assert statuses[-1] == 429


async def test_an_unconfigured_key_reads_plainly(signed_in, monkeypatch):
    monkeypatch.setattr(settings, "unsplash_access_key", SecretStr(""))
    with pytest.raises(unsplash_service.UnsplashError) as info:
        await unsplash_service.search("hempcrete")
    assert str(info.value) == IMAGE_SEARCH_UNAVAILABLE_COPY
    assert "UNSPLASH_ACCESS_KEY" not in str(info.value)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/api/images/unsplash/search", params={"q": "hempcrete"})
    assert r.status_code == 502
    assert r.json()["detail"] == IMAGE_SEARCH_UNAVAILABLE_COPY
    assert IMAGE_SEARCH_UNAVAILABLE_COPY == (
        "Image search isn't available right now. You can still use the brand images."
    )


async def test_an_upstream_failure_reads_plainly_too(signed_in, monkeypatch):
    monkeypatch.setattr(settings, "unsplash_access_key", SecretStr("test-key"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"errors": ["Rate Limit Exceeded"]})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **k: real_client(transport=httpx.MockTransport(handler), **k),
    )
    async with real_client(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/api/images/unsplash/search", params={"q": "hempcrete"})
    assert r.status_code == 502
    assert r.json()["detail"] == IMAGE_SEARCH_UNAVAILABLE_COPY
