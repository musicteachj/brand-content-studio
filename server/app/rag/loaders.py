"""Document loaders → plain text sections.

Markdown/plain text load as a single section; PDFs load one section per page
(so chunks can carry a `page` for the debug panel). Uploaded brand docs are
*untrusted* input: page count is capped to bound parse time / avoid a
malicious-file DoS (ARCHITECTURE gotcha #9)."""
from __future__ import annotations

from dataclasses import dataclass

from app.limits import MAX_PDF_PAGES


class UnsupportedFileError(ValueError):
    pass


class FileTooComplexError(ValueError):
    pass


@dataclass
class Section:
    text: str
    page: int | None = None


def load_sections(path: str, content_type: str) -> list[Section]:
    if content_type == "application/pdf":
        return _load_pdf(path)
    if content_type in ("text/markdown", "text/plain", "text/x-markdown"):
        return _load_text(path)
    raise UnsupportedFileError("This file type can't be ingested. Upload a PDF, Markdown, or plain-text file.")


def _load_text(path: str) -> list[Section]:
    with open(path, encoding="utf-8", errors="replace") as f:
        return [Section(text=f.read(), page=None)]


def _load_pdf(path: str) -> list[Section]:
    import pdfplumber

    sections: list[Section] = []
    with pdfplumber.open(path) as pdf:
        if len(pdf.pages) > MAX_PDF_PAGES:
            raise FileTooComplexError(
                f"PDF has {len(pdf.pages)} pages; the limit is {MAX_PDF_PAGES}."
            )
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                sections.append(Section(text=text, page=i))
    return sections
