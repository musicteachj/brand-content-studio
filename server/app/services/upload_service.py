"""The single untrusted-upload boundary (ARCH-01).

Before this, the `read → empty(400) → size(413)` triad plus five different
content-type / extension checks were copy-pasted across nine route handlers.
Centralizing them here means one place validates every upload — so the security
posture (size caps, allowed types) is auditable in one file, and a new upload
route can't drift or forget a check. The OOXML zip-bomb guard is deliberately NOT
here: it lives in the parsing layer (`utils/archives.assert_safe_ooxml`, called
from `template_service`/`content_extraction`) so it can't be bypassed by a route
that reads bytes without parsing them.
"""
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from fastapi import HTTPException, UploadFile, status

from app.limits import (
    MAX_ASSET_BYTES,
    MAX_FONT_BYTES,
    MAX_IMAGE_BYTES,
    MAX_SOURCE_BYTES,
    MAX_TEMPLATE_BYTES,
)

T = TypeVar("T")


# --- Type validators (each raises 415 on a bad type) ---------------------------
IMAGE_CONTENT_TYPE = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
_IMAGE_ALLOWED = set(IMAGE_CONTENT_TYPE.values())


def resolve_image_content_type(filename: str, provided: str | None) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in IMAGE_CONTENT_TYPE:
        return IMAGE_CONTENT_TYPE[ext]
    if provided in _IMAGE_ALLOWED:
        return provided  # type: ignore[return-value]
    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Unsupported image type. Upload a JPG, PNG, or WebP.",
    )


# Map common extensions → canonical content types (browsers are inconsistent,
# e.g. .md often arrives as application/octet-stream).
_ASSET_CONTENT_TYPE = {
    ".pdf": "application/pdf",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
}
_ASSET_ALLOWED = set(_ASSET_CONTENT_TYPE.values())


def resolve_asset_content_type(filename: str, provided: str | None) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in _ASSET_CONTENT_TYPE:
        return _ASSET_CONTENT_TYPE[ext]
    if provided in _ASSET_ALLOWED:
        return provided  # type: ignore[return-value]
    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Unsupported file type. Upload a PDF, Markdown, or plain-text file.",
    )


_TEMPLATE_FORMAT_BY_EXT = {".docx": "docx", ".pptx": "pptx"}


def resolve_template_format(filename: str, provided: str | None = None) -> str:
    fmt = _TEMPLATE_FORMAT_BY_EXT.get(os.path.splitext(filename)[1].lower())
    if not fmt:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported template. Upload a .docx or .pptx file.",
        )
    return fmt


SOURCE_EXTS = {".docx", ".pptx", ".pdf", ".txt", ".md", ".markdown"}


def resolve_source(filename: str, provided: str | None = None) -> None:
    if os.path.splitext(filename)[1].lower() not in SOURCE_EXTS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported document. Upload a .docx, .pptx, .pdf, .txt, or .md file.",
        )
    return None


def resolve_font(filename: str, provided: str | None = None) -> None:
    if not filename.lower().endswith(".ttf"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported font. Upload a .ttf file.",
        )
    return None


# --- The policies + the one gate ----------------------------------------------
@dataclass(frozen=True)
class UploadPolicy(Generic[T]):
    """The frozen per-file-class contract: size cap, 413 noun, and a type validator
    that raises 415 and returns the resolved value (media type / format / None)."""

    max_bytes: int
    noun: str  # 413 message: f"{noun} exceeds the {mb} MB limit."
    validate_type: Callable[[str, str | None], T]


IMAGE_POLICY = UploadPolicy(MAX_IMAGE_BYTES, "Image", resolve_image_content_type)
ASSET_POLICY = UploadPolicy(MAX_ASSET_BYTES, "File", resolve_asset_content_type)
TEMPLATE_POLICY = UploadPolicy(MAX_TEMPLATE_BYTES, "Template", resolve_template_format)
SOURCE_POLICY = UploadPolicy(MAX_SOURCE_BYTES, "Document", resolve_source)
FONT_POLICY = UploadPolicy(MAX_FONT_BYTES, "Font", resolve_font)


async def read_upload(
    file: UploadFile, policy: UploadPolicy[T], *, default_name: str
) -> tuple[bytes, str, T]:
    """Validate type (415) → read → reject empty (400) → enforce the size cap (413).
    Returns `(data, filename, resolved)` where `resolved` is the type validator's
    value (media type / template format / None). Type is checked before the file
    is read so a bad type is rejected without buffering the bytes."""
    filename = file.filename or default_name
    resolved = policy.validate_type(filename, file.content_type)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file.")
    if len(data) > policy.max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{policy.noun} exceeds the {policy.max_bytes // (1024 * 1024)} MB limit.",
        )
    return data, filename, resolved
