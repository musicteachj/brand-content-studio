"""Zip-bomb guard for OOXML (.docx/.pptx) uploads.

Both formats are ZIP containers, and every upload cap in the app measures the
*compressed* size. A crafted 48 KB .docx expands to a 50 MB document.xml (~1000x),
so a file that passes the 10 MB cap can still claim gigabytes of RAM inside
python-docx/python-pptx. Check the declared uncompressed sizes before handing
bytes to any parser.

Called from the parsing layer (template_service, content_extraction) rather than
from routes, so a new upload endpoint cannot forget it.
"""
from __future__ import annotations

import zipfile
from io import BytesIO

from app.limits import MAX_COMPRESSION_RATIO, MAX_UNCOMPRESSED_BYTES


class UnsafeArchive(ValueError):
    """An OOXML upload that expands beyond the safety bounds (413), or, as the
    `UnreadableArchive` subclass, isn't a ZIP at all (422). Routes answer with
    `exc.status_code` so the two never get mixed up."""

    status_code = 413


class UnreadableArchive(UnsafeArchive):
    """The upload isn't a ZIP at all: a bad file, not an oversized one (QA-13)."""

    status_code = 422


def assert_safe_ooxml(data: bytes) -> None:
    """Raise UnreadableArchive if `data` is not a readable ZIP, or UnsafeArchive if
    it would decompress to more than MAX_UNCOMPRESSED_BYTES / MAX_COMPRESSION_RATIO."""
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            total = sum(info.file_size for info in zf.infolist())
    except zipfile.BadZipFile as exc:
        raise UnreadableArchive("File is not a readable .docx/.pptx archive.") from exc

    if total > MAX_UNCOMPRESSED_BYTES:
        raise UnsafeArchive(
            f"File expands to {total // (1024 * 1024)} MB, over the "
            f"{MAX_UNCOMPRESSED_BYTES // (1024 * 1024)} MB limit."
        )
    if data and total / len(data) > MAX_COMPRESSION_RATIO:
        raise UnsafeArchive("File's compression ratio is implausibly high.")
