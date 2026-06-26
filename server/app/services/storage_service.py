"""Storage abstraction. Local filesystem for dev; S3 swaps in for prod behind
the same `StorageBackend` protocol (DECISIONS #13). Storage keys are derived
server-side (never from raw client filenames) and every read/write is confined
to the storage root — a path-traversal guard, since filenames are untrusted."""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.config import settings

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(filename: str) -> str:
    """Strip path components and unsafe chars so a filename can't escape its dir."""
    base = os.path.basename(filename).replace("\\", "/").split("/")[-1]
    cleaned = _SAFE.sub("_", base).strip("._") or "file"
    return cleaned[:200]


def build_storage_key(workspace_id: str, asset_id: str, filename: str) -> str:
    return f"{workspace_id}/{asset_id}/{safe_filename(filename)}"


def build_image_key(workspace_id: str, image_id: str, filename: str) -> str:
    """Uploaded card images live under an `images/` prefix, separate from the
    ingested asset corpus."""
    return f"{workspace_id}/images/{image_id}/{safe_filename(filename)}"


class StorageBackend(Protocol):
    async def save(self, key: str, data: bytes) -> None: ...
    async def read(self, key: str) -> bytes: ...
    def local_path(self, key: str) -> str: ...  # for sync parsers (pdfplumber)
    async def delete(self, key: str) -> None: ...
    async def delete_prefix(self, prefix: str) -> None: ...


class LocalStorage:
    def __init__(self) -> None:
        self._root = Path(settings.storage_local_dir).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        target = (self._root / key).resolve()
        # Confine to the storage root — reject any key that escapes it.
        if self._root != target and self._root not in target.parents:
            raise ValueError(f"Illegal storage key escapes root: {key!r}")
        return target

    async def save(self, key: str, data: bytes) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def read(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def local_path(self, key: str) -> str:
        return str(self._resolve(key))

    async def delete(self, key: str) -> None:
        try:
            self._resolve(key).unlink(missing_ok=True)
        except ValueError:
            pass

    async def delete_prefix(self, prefix: str) -> None:
        base = self._resolve(prefix)
        if base.is_dir():
            import shutil

            shutil.rmtree(base, ignore_errors=True)


@lru_cache(maxsize=1)
def get_storage() -> StorageBackend:
    if settings.storage_backend == "local":
        return LocalStorage()
    raise ValueError(f"Unsupported storage_backend: {settings.storage_backend!r}")
