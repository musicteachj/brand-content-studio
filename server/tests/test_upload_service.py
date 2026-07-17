"""The consolidated upload gate (ARCH-01). `read_upload` is the single
read → empty(400) → size(413) path; each `UploadPolicy` carries the per-class
size cap, 413 noun, and type validator (415)."""
from dataclasses import replace
from io import BytesIO

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

from app.services.upload_service import (
    ASSET_POLICY,
    FONT_POLICY,
    IMAGE_POLICY,
    SOURCE_POLICY,
    TEMPLATE_POLICY,
    read_upload,
)


def _upload(data: bytes, filename: str, content_type: str | None = None) -> UploadFile:
    headers = Headers({"content-type": content_type}) if content_type else None
    return UploadFile(file=BytesIO(data), filename=filename, headers=headers)


async def test_read_upload_returns_bytes_filename_and_resolved_type():
    data, filename, resolved = await read_upload(
        _upload(b"PNGDATA", "logo.png", "image/png"), IMAGE_POLICY, default_name="image"
    )
    assert data == b"PNGDATA"
    assert filename == "logo.png"
    assert resolved == "image/png"  # image policy resolves the canonical media type


async def test_read_upload_empty_is_400():
    with pytest.raises(HTTPException) as exc:
        await read_upload(_upload(b"", "logo.png", "image/png"), IMAGE_POLICY, default_name="image")
    assert exc.value.status_code == 400
    assert exc.value.detail == "Empty file."


async def test_read_upload_oversize_is_413_with_policy_noun():
    tiny = replace(IMAGE_POLICY, max_bytes=4)
    with pytest.raises(HTTPException) as exc:
        await read_upload(_upload(b"way too big", "a.png", "image/png"), tiny, default_name="image")
    assert exc.value.status_code == 413
    assert "Image exceeds" in exc.value.detail  # noun comes from the policy


async def test_read_upload_bad_type_is_415_before_read():
    # A bad-type *empty* file must 415 (type validated before the empty/size checks).
    with pytest.raises(HTTPException) as exc:
        await read_upload(_upload(b"", "a.gif", "image/gif"), IMAGE_POLICY, default_name="image")
    assert exc.value.status_code == 415


async def test_read_upload_falls_back_to_default_name():
    _, filename, _ = await read_upload(
        _upload(b"X", "a.png", "image/png"), IMAGE_POLICY, default_name="image"
    )
    assert filename == "a.png"
    _, filename2, _ = await read_upload(
        _upload(b"X", "", "image/png"), IMAGE_POLICY, default_name="fallback"
    )
    assert filename2 == "fallback"


def test_policy_validators_accept_and_reject():
    # Each validator returns its resolved value for a good name and raises 415 otherwise.
    assert IMAGE_POLICY.validate_type("a.png", None) == "image/png"
    assert ASSET_POLICY.validate_type("a.pdf", None) == "application/pdf"
    assert TEMPLATE_POLICY.validate_type("deck.pptx", None) == "pptx"
    assert SOURCE_POLICY.validate_type("brief.md", None) is None  # membership check, no value
    assert FONT_POLICY.validate_type("brand.ttf", None) is None

    for policy, bad in [
        (IMAGE_POLICY, "a.gif"),
        (ASSET_POLICY, "a.docx"),
        (TEMPLATE_POLICY, "a.png"),
        (SOURCE_POLICY, "a.exe"),
        (FONT_POLICY, "a.otf"),
    ]:
        with pytest.raises(HTTPException) as exc:
            policy.validate_type(bad, None)
        assert exc.value.status_code == 415


def test_policy_size_caps_match_the_originals():
    assert IMAGE_POLICY.max_bytes == 8 * 1024 * 1024
    assert ASSET_POLICY.max_bytes == 10 * 1024 * 1024
    assert TEMPLATE_POLICY.max_bytes == 10 * 1024 * 1024
    assert SOURCE_POLICY.max_bytes == 10 * 1024 * 1024
    assert FONT_POLICY.max_bytes == 5 * 1024 * 1024
