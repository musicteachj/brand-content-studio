"""The seed's generated demo assets (Phase 5 demo enrichment). The templates must
expose discoverable {{placeholders}} so the seeded Templates page is actually
usable, and the generated images must be valid PNGs."""
from io import BytesIO

from PIL import Image

from app.services.template_service import discover_placeholders
from seed.seed_demo import (
    _generate_card,
    _generate_docx_template,
    _generate_logo,
    _generate_pptx_template,
)


def test_seed_docx_template_has_expected_placeholders():
    found = discover_placeholders(_generate_docx_template(), "docx")
    assert set(found) == {
        "client_name",
        "date",
        "next_steps",
        "prepared_by",
        "project_title",
        "summary",
    }


def test_seed_pptx_template_has_expected_placeholders():
    found = discover_placeholders(_generate_pptx_template(), "pptx")
    assert found == ["title", "subtitle", "section_title", "point_1", "point_2", "point_3"]


def test_seed_logo_is_valid_png():
    img = Image.open(BytesIO(_generate_logo()))
    assert img.format == "PNG"
    assert img.size == (480, 480)


def test_seed_card_is_portrait_png():
    img = Image.open(BytesIO(_generate_card("Material notes", "The carbon math is changing")))
    assert img.format == "PNG"
    assert img.size == (1080, 1350)
