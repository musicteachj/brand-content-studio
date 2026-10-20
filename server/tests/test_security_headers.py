"""Security headers, including the Content-Security-Policy (known-gaps plan, step 2).
A tiny app wrapped in the real middleware keeps these independent of Mongo."""
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.config import settings
from app.main import SecurityHeadersMiddleware


def _client() -> TestClient:
    inner = FastAPI()

    @inner.get("/ping")
    async def ping():
        return {"ok": True}

    @inner.get("/stream")
    async def stream():
        async def frames():
            for i in range(3):
                yield f"data: {i}\n\n"

        return StreamingResponse(frames(), media_type="text/event-stream")

    return TestClient(SecurityHeadersMiddleware(inner))


def _directives(header: str) -> dict[str, list[str]]:
    out = {}
    for part in header.split(";"):
        name, *values = part.split()
        out[name] = values
    return out


def test_enforcing_csp_is_sent_by_default():
    resp = _client().get("/ping")
    assert "content-security-policy-report-only" not in resp.headers
    d = _directives(resp.headers["content-security-policy"])
    assert d["default-src"] == ["'self'"]
    # WebAssembly (resvg export, satori layout) only; never general eval or inline script.
    assert d["script-src"] == ["'self'", "'wasm-unsafe-eval'"]
    assert d["object-src"] == ["'none'"]
    assert d["base-uri"] == ["'self'"]
    assert d["form-action"] == ["'self'"]
    assert d["frame-ancestors"] == ["'none'"]
    assert "https://cdn.jsdelivr.net" in d["font-src"]  # card fonts
    assert "https://images.unsplash.com" in d["img-src"]


def test_the_other_baseline_headers_are_unchanged():
    h = _client().get("/ping").headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert h["referrer-policy"] == "strict-origin-when-cross-origin"


def test_report_only_mode(monkeypatch):
    monkeypatch.setattr(settings, "csp_mode", "report-only")
    h = _client().get("/ping").headers
    assert "content-security-policy" not in h
    assert "default-src 'self'" in h["content-security-policy-report-only"]


def test_off_mode_sends_no_csp(monkeypatch):
    monkeypatch.setattr(settings, "csp_mode", "off")
    h = _client().get("/ping").headers
    assert "content-security-policy" not in h
    assert "content-security-policy-report-only" not in h


def test_streams_still_stream_with_the_csp():
    with _client().stream("GET", "/stream") as resp:
        assert "content-security-policy" in resp.headers
        assert list(resp.iter_lines()) == ["data: 0", "", "data: 1", "", "data: 2", ""]


def test_an_unknown_mode_is_rejected():
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, csp_mode="sometimes")
    assert [e["loc"] for e in exc.value.errors()] == [("csp_mode",)]


def test_the_real_app_sends_the_csp():
    from app.main import app

    resp = TestClient(app).get("/api/does-not-exist")  # no route, no database
    assert "default-src 'self'" in resp.headers["content-security-policy"]


def test_fastapis_docs_pages_are_exempt():
    from app.main import app

    client = TestClient(app)
    for path in ("/docs", "/redoc"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert "content-security-policy" not in resp.headers, path
        assert resp.headers["x-frame-options"] == "DENY"  # the rest still apply
