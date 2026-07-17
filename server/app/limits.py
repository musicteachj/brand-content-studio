"""Central registry of the app's DoS / upload ceilings — every "how big, how
many, how long" cap that bounds work on untrusted input, in one place (audit
ARCH-05). Enforcement stays in each consuming module; only the numbers live here,
so "what are our limits?" is one file to read and tune, not six.

Deliberately EXCLUDES domain/token caps that are inseparable from their logic:
the Claude `*_MAX_TOKENS` budgets (`ai_service`, `brand_extract_service`), the
template-shape caps (`template_service.MAX_PLACEHOLDERS` / `MAX_VALUE_LEN`), the
rate-limit and demo-quota knobs (already centralized in `config.Settings`), and
outbound HTTP client timeouts (`unsplash_service`).

Imports nothing from `app`, so any module can import it without a cycle.
"""
from __future__ import annotations

MB = 1024 * 1024

# --- Upload byte caps (per file class; enforced by upload_service.UploadPolicy) -
MAX_IMAGE_BYTES = 8 * MB      # logos, exemplars, brand images, card uploads
MAX_ASSET_BYTES = 10 * MB     # ingested PDF/MD/TXT source assets
MAX_TEMPLATE_BYTES = 10 * MB  # .docx/.pptx templates
MAX_SOURCE_BYTES = 10 * MB    # fill-from-document source
MAX_FONT_BYTES = 5 * MB       # uploaded .ttf brand fonts

# --- Collection count caps (brand_profile sub-collections; enforced atomically
# in workspace_service) --------------------------------------------------------
MAX_EXEMPLARS = 5
MAX_BRAND_IMAGES = 24
MAX_UPLOADED_FONTS = 8
MAX_CARD_PRESETS = 8

# --- Upload-processing DoS caps (bound work on untrusted files) ----------------
MAX_UNCOMPRESSED_BYTES = 100 * MB  # zip-bomb: summed uncompressed size of OOXML members
MAX_COMPRESSION_RATIO = 100        # zip-bomb: uncompressed : compressed
MAX_PDF_PAGES = 80                 # page cap for PDF parsing (loaders + content_extraction)
MAX_CHUNKS = 400                   # ingestion: reject (not truncate) a doc beyond this
MAX_SOURCE_CHARS = 40_000          # fill-from-document: extracted-text cap (~10-12 pages)

# Parse-time budgets for off-loop (to_thread) parsing of untrusted uploads. Two
# constants (same value today) because they guard independent flows and may diverge.
PARSE_TIMEOUT_S = 30         # asset ingestion (ingestion_service)
SOURCE_PARSE_TIMEOUT_S = 30  # fill-from-document source (routes/templates)
