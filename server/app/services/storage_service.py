"""Storage abstraction. Local filesystem for dev; S3 swaps in for prod behind
the same `StorageBackend` protocol (DECISIONS #13). Storage keys are derived
server-side (never from raw client filenames) and every read/write is confined
to the storage root — a path-traversal guard, since filenames are untrusted."""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.config import settings

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


_OBJECT_ID = re.compile(r"[0-9a-f]{24}")


def is_object_id_str(value: str) -> bool:
    """True for the exact form `str(ObjectId())` makes (24 lowercase hex), the only shape
    image and font ids are created in. Ids are stored lowercase, so file URLs are
    case-sensitive on purpose: an uppercase spelling is not the same file."""
    return _OBJECT_ID.fullmatch(value) is not None


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


def build_font_key(workspace_id: str, font_id: str, filename: str) -> str:
    """Uploaded brand fonts live under a `fonts/` prefix, separate from card
    images and the ingested corpus."""
    return f"{workspace_id}/fonts/{font_id}/{safe_filename(filename)}"


# Generated documents (Phase 2). Allow-listed formats only; the key is fully
# server-derived from (workspace, generation, format), so the download route
# never trusts a stored or client-supplied key — it rebuilds this and reads it.
DOCUMENT_FORMATS = ("docx", "pdf", "pptx")


def build_workspace_prefix(workspace_id: str) -> str:
    """Every file a workspace owns (assets, images, fonts, templates, documents) lives
    under this prefix."""
    return safe_filename(workspace_id)


def build_document_prefix(workspace_id: str, generation_id: str) -> str:
    """Everything built for one generation lives under this prefix."""
    return f"{safe_filename(workspace_id)}/documents/{safe_filename(generation_id)}"


def build_document_key(workspace_id: str, generation_id: str, fmt: str) -> str:
    if fmt not in DOCUMENT_FORMATS:
        raise ValueError(f"Unsupported document format: {fmt!r}")
    return f"{build_document_prefix(workspace_id, generation_id)}/document.{fmt}"


def build_template_key(workspace_id: str, template_id: str, filename: str) -> str:
    """Uploaded fill-in templates live under a `templates/` prefix, separate from
    the ingested corpus, card images, and generated documents."""
    return f"{safe_filename(workspace_id)}/templates/{safe_filename(template_id)}/{safe_filename(filename)}"


class StorageNotWritable(RuntimeError):
    """A data directory the app must write to (storage, Chroma) isn't writable by the
    user the app runs as, such as a volume still owned by another uid."""


def assert_writable(path: Path) -> None:
    """Create `path` if needed, then create and delete a probe file in it. Run at startup
    so a wrongly owned volume stops the app with the directory's name, instead of failing
    on a visitor's first upload."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        fd, probe = tempfile.mkstemp(prefix=".write-probe-", dir=path)
        os.close(fd)
        os.unlink(probe)
    except OSError as exc:
        raise StorageNotWritable(f"{path} is not writable by uid {os.getuid()}") from exc


class StorageBackend(Protocol):
    async def save(self, key: str, data: bytes) -> None: ...
    async def read(self, key: str) -> bytes: ...
    def local_path(self, key: str) -> str: ...  # for sync parsers (pdfplumber)
    async def delete(self, key: str) -> None: ...
    # `strict=True` raises when anything under the prefix couldn't be removed; the default
    # is best effort (errors ignored), for request paths where a leftover file is harmless.
    async def delete_prefix(self, prefix: str, *, strict: bool = False) -> None: ...
    # Each document folder (`<workspace>/documents/<generation>`) last changed before
    # `older_than`, as a prefix; the cleanup job looks for ones no record points at.
    async def document_prefixes_before(self, older_than: datetime) -> list[str]: ...


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

    async def delete_prefix(self, prefix: str, *, strict: bool = False) -> None:
        base = self._resolve(prefix)
        if not strict:
            if base.is_dir():
                # Off the event loop: a generation delete now does this on the request path.
                await asyncio.to_thread(shutil.rmtree, base, True)
            return
        # Strict (the cleanup job): a failed removal raises, and so does anything still
        # there afterward, so the caller keeps the record that points at these files.
        if base.exists():
            await asyncio.to_thread(shutil.rmtree, base)
        if base.exists():
            raise OSError(f"Storage prefix still present after delete: {prefix!r}")

    async def document_prefixes_before(self, older_than: datetime) -> list[str]:
        cutoff = older_than.timestamp()

        def scan() -> list[str]:
            # A folder that vanishes mid-scan (a delete on the request path) or can't be
            # read is skipped, so one odd entry never stops the cleanup run.
            found: list[str] = []
            for workspace in self._root.iterdir():
                documents = workspace / "documents"
                try:
                    folders = list(documents.iterdir()) if documents.is_dir() else []
                except OSError:
                    continue
                for folder in folders:
                    try:
                        if folder.is_dir() and folder.stat().st_mtime < cutoff:
                            found.append(f"{workspace.name}/documents/{folder.name}")
                    except OSError:
                        continue
            return found

        return await asyncio.to_thread(scan)


@lru_cache(maxsize=1)
def get_storage() -> StorageBackend:
    if settings.storage_backend == "local":
        return LocalStorage()
    raise ValueError(f"Unsupported storage_backend: {settings.storage_backend!r}")
