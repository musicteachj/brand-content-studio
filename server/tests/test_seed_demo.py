"""The seed's generated demo assets (Phase 5 demo enrichment). The templates must
expose discoverable {{placeholders}} so the seeded Templates page is actually
usable, and the generated images must be valid PNGs."""
from io import BytesIO

from PIL import Image

from app.services.template_service import discover_placeholders
from seed.seed_demo import (
    _generate_brand_image,
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


def test_seed_brand_image_is_valid_png():
    img = Image.open(BytesIO(_generate_brand_image("Forest texture")))
    assert img.format == "PNG"
    assert img.size == (1080, 1350)


def test_seed_report_is_ok_without_an_error():
    from seed.seed_demo import SeedReport

    assert SeedReport(created=[], repaired=[], error=None).ok
    assert not SeedReport(created=["workspace"], repaired=[], error="out of date").ok


def test_cli_takes_embed_missing_and_says_to_stop_the_api_first():
    from seed import seed_demo

    assert seed_demo.parse_args([]).embed_missing is False
    assert seed_demo.parse_args(["--embed-missing"]).embed_missing is True
    assert "stop the API" in (seed_demo.__doc__ or "")


def test_cli_report_lists_what_was_created_and_repaired():
    from seed.seed_demo import SeedReport, format_report

    text = format_report(SeedReport(created=["workspace"], repaired=["logo file"], error=None))
    assert "workspace" in text and "logo file" in text
    assert "nothing to repair" in format_report(SeedReport(created=[], repaired=[], error=None))
    assert "out of date" in format_report(SeedReport(created=[], repaired=[], error="out of date"))


def test_seeded_voice_summary_has_no_em_dash():
    from seed.seed_demo import VERDURE_BRAND_PROFILE

    assert "\u2014" not in VERDURE_BRAND_PROFILE["voice_summary"]
