"""Visitors never see an em dash in the copy and fixtures this plan adds: the examples
fixture, every `*_COPY` constant on the server, and the new visitor pages in the client.
(Older copy elsewhere is out of scope.)"""
from __future__ import annotations

import importlib
from pathlib import Path

from seed.seed_demo import EXAMPLES_FIXTURE

EM_DASH = "\u2014"
SERVER_DIR = Path(__file__).resolve().parents[1]
CLIENT_SRC = SERVER_DIR.parent / "client" / "src"

# The client files this plan adds. Each one is scanned once it exists.
CLIENT_FILES = ("StartPage.tsx", "ExamplesPage.tsx", "PrivacyPage.tsx", "GenerationError.tsx")


def _copy_constants() -> dict[str, str]:
    modules = ["app.utils.errors"] + [
        f"app.routes.{p.stem}"
        for p in sorted((SERVER_DIR / "app" / "routes").glob("*.py"))
        if p.stem != "__init__"
    ]
    found: dict[str, str] = {}
    for name in modules:
        module = importlib.import_module(name)
        for attr, value in vars(module).items():
            if attr.endswith("_COPY") and isinstance(value, str):
                found[f"{name}.{attr}"] = value
    return found


def _client_files() -> list[Path]:
    return [path for name in CLIENT_FILES for path in CLIENT_SRC.rglob(name)]


def test_no_em_dashes_in_visitor_copy_or_fixtures():
    texts = {str(EXAMPLES_FIXTURE): EXAMPLES_FIXTURE.read_text(encoding="utf-8")}
    copy = _copy_constants()
    assert "app.utils.errors.LIVE_AI_PAUSED_COPY" in copy
    texts.update(copy)
    for path in _client_files():
        texts[str(path)] = path.read_text(encoding="utf-8")

    offenders = [where for where, text in texts.items() if EM_DASH in text]
    assert offenders == []
