"""QA-2026-10 Low findings in prompts and rendering: no Markdown emphasis in posts
(QA-05), a one-pager that fits one PDF page (QA-09), and template drafts that
leave unknowns blank instead of writing placeholders or inventing dates (QA-11)."""
import io
from datetime import date

from pypdf import PdfReader

from app.models.generation import DocumentArchetype
from app.prompts import document, template_fill, text_post
from app.services import document_service, template_service

BRAND_PROFILE = {
    "colors": [{"name": "Forest", "hex": "#1C3A2E", "role": "primary"}],
    "fonts": {"heading": "DM Serif Display", "body": "Inter"},
}


# --- QA-05 -------------------------------------------------------------------
def test_text_post_forbids_markdown_emphasis():
    system = text_post.build_system(None)
    assert "**" in system  # names the bold marker it forbids
    assert "bold" in system.lower() and "italic" in system.lower()


# --- QA-09 -------------------------------------------------------------------
def test_one_pager_guidance_has_a_word_budget():
    guidance = document.build_copy_user("brief", DocumentArchetype.one_pager, "default", [])
    assert "300 words" in guidance


_SENTENCE = "Hempcrete stores carbon in the wall for the life of the building. "  # 13 words


def _one_pager(words_per_body: int, sections: int = 3) -> dict:
    body = (_SENTENCE * (words_per_body // 13 + 1)).split()[:words_per_body]
    body = " ".join(body)
    return {
        "archetype": "one-pager",
        "title": "Three materials, one wall",
        "eyebrow": "Material comparison",
        "lede": "How hempcrete, reclaimed timber, and recycled steel compare on embodied carbon.",
        "sections": [
            {"heading": f"Section {i}", "body": body, "bullets": ["One point", "Another point"]}
            for i in range(sections)
        ],
        "footer": "Verdure Materials · verdure.materials",
    }


def _pages(pdf: bytes) -> int:
    return len(PdfReader(io.BytesIO(pdf)).pages)


def test_short_one_pager_fits_one_page():
    assert _pages(document_service.render_pdf(_one_pager(60), BRAND_PROFILE)) == 1


def test_overlong_one_pager_is_scaled_onto_one_page():
    # ~450 words: two pages at full size (QA-09 reproduced at 378 and 572).
    assert _pages(document_service.render_pdf(_one_pager(130), BRAND_PROFILE)) == 1


def test_one_pager_too_long_to_fit_keeps_full_size_type():
    # Past the readability floor, shrinking can't save a page, so it renders at full
    # size (3 pages here) rather than small type that still spills over.
    assert _pages(document_service.render_pdf(_one_pager(300, sections=4), BRAND_PROFILE)) == 3


# --- QA-11 -------------------------------------------------------------------
def test_fill_system_says_to_leave_unknowns_blank():
    system = template_fill.build_fill_system().lower()
    assert "leave" in system and "empty" in system
    assert "<unknown>" in system  # names the placeholder it must not write


def test_fill_user_gives_todays_date():
    user = template_fill.build_fill_user("brief", ["date"], today=date(2026, 10, 20))
    assert "October 20, 2026" in user


def test_fill_from_document_gives_todays_date():
    user = template_fill.build_fill_user_from_content("text", ["date"], today=date(2026, 10, 20))
    assert "October 20, 2026" in user


def test_ai_values_drop_placeholder_tokens():
    cleaned = template_service.scrub_ai_values(
        {"author": "<UNKNOWN>", "client": "[Client name]", "date": "TBD", "title": "Hempcrete"}
    )
    assert cleaned == {"author": "", "client": "", "date": "", "title": "Hempcrete"}


def test_ai_values_keep_real_short_answers():
    values = {"discount": "N/A", "status": "Unknown", "note": "Prepared by Verdure"}
    assert template_service.scrub_ai_values(values) == values
