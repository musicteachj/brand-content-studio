"""Uploaded brand fonts: model + service + (later) routes / PDF embedding."""
import pytest

from app.models.common import BrandProfile, UploadedFont
from app.services.storage_service import build_font_key
from app.services.workspace_service import resolve_uploaded_font


def test_uploaded_font_default_empty():
    assert BrandProfile().uploaded_fonts == []


def test_uploaded_font_shape():
    f = UploadedFont(id="f1", family="Acme Sans", storage_key="k", url="/u")
    assert f.family == "Acme Sans"


def test_build_font_key_is_server_derived():
    assert build_font_key("ws1", "f1", "Acme Sans.ttf") == "ws1/fonts/f1/Acme_Sans.ttf"


def test_resolve_uploaded_font_matches_family():
    bp = {"uploaded_fonts": [{"id": "f1", "family": "Acme Sans", "storage_key": "k1", "url": "/u"}]}
    assert resolve_uploaded_font(bp, "Acme Sans") == "k1"
    assert resolve_uploaded_font(bp, "Inter") is None
    assert resolve_uploaded_font({}, "Acme Sans") is None
