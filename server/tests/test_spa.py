"""Production SPA serving (known-gaps plan, step 0). The built client loads
`/assets/*.js` and `/assets/*.css`; the old catch-all answered those with
index.html as text/html, so browsers refused them and the page stayed blank."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.spa import mount_spa

INDEX = '<!doctype html><div id="root"></div><script type="module" src="/assets/index-abc12345.js"></script>'


@pytest.fixture
def client(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX)
    (dist / "assets" / "index-abc12345.js").write_text("console.log('app')")
    (dist / "assets" / "index-abc12345.css").write_text("body{}")
    (dist / "favicon.svg").write_text("<svg/>")
    (dist / "assets" / "logo.png").write_text("not hashed")
    (dist / "assets" / "inter-latin-400-AbCd1234.woff2").write_bytes(b"wOF2")
    (dist / ".env").write_text("SECRET=1")
    (tmp_path / "secret.txt").write_text("outside dist")

    app = FastAPI()

    @app.get("/api/health")
    async def health():  # stands in for the real API routers, registered first
        return {"status": "ok"}

    mount_spa(app, dist)
    return TestClient(app)


def test_built_js_is_served_as_javascript(client):
    resp = client.get("/assets/index-abc12345.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]
    assert resp.text == "console.log('app')"
    assert "immutable" in resp.headers["cache-control"]  # hashed names never change


def test_built_css_is_served_as_css(client):
    resp = client.get("/assets/index-abc12345.css")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/css")


def test_missing_asset_is_404_not_index_html(client):
    assert client.get("/assets/index-oldhash1.js").status_code == 404


def test_client_routes_get_index_html(client):
    for path in ("/", "/login", "/generate", "/history"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert 'id="root"' in resp.text
        assert resp.headers["cache-control"] == "no-cache"  # a deploy's new hashes load at once


def test_root_level_files_are_served_as_files(client):
    resp = client.get("/favicon.svg")
    assert resp.status_code == 200
    assert resp.text == "<svg/>"


def test_unknown_api_path_is_a_json_404(client):
    resp = client.get("/api/nope")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/json")
    assert client.get("/api/health").json() == {"status": "ok"}


def test_paths_outside_dist_are_never_served(client):
    resp = client.get("/%2e%2e/secret.txt")
    assert "outside dist" not in resp.text


def test_index_html_by_name_is_also_no_cache(client):
    assert client.get("/index.html").headers["cache-control"] == "no-cache"


def test_assets_client_route_with_a_trailing_slash_is_the_spa(client):
    # /assets is also the Assets page; a typed or proxied trailing slash must not 404.
    for path in ("/assets", "/assets/"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert 'id="root"' in resp.text


def test_head_works_for_client_routes_and_files(client):
    assert client.head("/").status_code == 200
    assert client.head("/login").status_code == 200
    assert client.head("/assets/index-abc12345.js").status_code == 200


def test_unknown_api_path_is_a_404_for_any_method_and_case(client):
    for method, path in (("POST", "/api/typo"), ("GET", "/API/workspaces"), ("DELETE", "/Api/x")):
        resp = client.request(method, path)
        assert resp.status_code == 404, (method, path)
        assert resp.headers["content-type"].startswith("application/json")


def test_dotfiles_are_never_served(client):
    resp = client.get("/.env")
    assert "SECRET" not in resp.text


def test_unhashed_files_under_assets_are_not_cached_forever(client):
    resp = client.get("/assets/logo.png")
    assert resp.status_code == 200
    assert "immutable" not in resp.headers.get("cache-control", "")


def test_a_dist_without_an_assets_folder_still_starts(tmp_path):
    (tmp_path / "index.html").write_text(INDEX)
    app = FastAPI()
    mount_spa(app, tmp_path)
    assert TestClient(app).get("/login").status_code == 200


def test_fonts_have_a_font_content_type(client):
    resp = client.get("/assets/inter-latin-400-AbCd1234.woff2")
    assert resp.headers["content-type"] == "font/woff2"
