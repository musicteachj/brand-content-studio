"""Serving the built client in production (the Docker image).

Vite builds with the default base, so `index.html` loads its bundle from
`/assets/<name>-<hash>.js|css`. Real files in `dist` are served as files; any
other path is a client route and gets `index.html`. An unknown `/api/...` path
stays a JSON 404 instead of quietly becoming the SPA. The old catch-all answered
`/assets/*` with index.html too, so browsers refused the bundle (text/html) and
the page stayed blank (known-gaps plan, step 0).

`index.html` is read once at startup and served from memory with the app's public origin
filled into its link-preview tags (`__APP_ORIGIN__`), since social crawlers need absolute URLs.

One StaticFiles subclass does it all, so HEAD, threadpool file lookups, and the
path-traversal guard come from Starlette.
"""
from __future__ import annotations

import mimetypes
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.responses import HTMLResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

# Slim images ship without /etc/mime.types, so fonts would go out as text/plain.
for _type, _ext in (("font/woff2", ".woff2"), ("font/woff", ".woff"), ("font/ttf", ".ttf")):
    mimetypes.add_type(_type, _ext)

# Vite names its output `<name>-<8-char hash>.<ext>`; only those can be cached for good.
_HASHED = re.compile(r"-[\w-]{8}\.\w+$")


class _SpaFiles(StaticFiles):
    def __init__(self, *, directory: Path, index_html: str) -> None:
        super().__init__(directory=directory)
        self._index_html = index_html

    async def get_response(self, path: str, scope: Scope) -> Response:
        if path.split("/", 1)[0].lower() == "api":
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if path in ("", ".", "index.html"):
            return self._index()
        if any(part.startswith(".") for part in path.split("/") if part != "."):
            return self._index()  # dotfiles are never served
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            # A missing bundle file is a real 404; anything else is a client route.
            if exc.status_code != 404 or (path.startswith("assets/") and _HASHED.search(path)):
                raise
            return self._index()
        if path.startswith("assets/") and _HASHED.search(path):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    def _index(self) -> Response:
        # index.html names the current hashed bundle, so always revalidate it.
        return HTMLResponse(self._index_html, headers={"Cache-Control": "no-cache"})


def mount_spa(app: FastAPI, dist_dir: Path, *, app_origin: str) -> None:
    """Serve `dist_dir` as the SPA. Call after every API router is included: the
    mount at `/` only sees paths no route claimed. `app_origin` is the public origin
    (any trailing slash is dropped) that replaces `__APP_ORIGIN__` in index.html."""
    index_html = (dist_dir / "index.html").read_text(encoding="utf-8")
    index_html = index_html.replace("__APP_ORIGIN__", app_origin.rstrip("/"))
    app.mount("/", _SpaFiles(directory=dist_dir, index_html=index_html), name="spa")
