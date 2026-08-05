"""PDF validation + deterministic text extraction (module §2, §3).

Two entry points, called from two different places on purpose:

- `validate_pdf_upload` — fast, synchronous, called from the API layer
  (app/api/v1/resumes.py) before anything is persisted. Rejects the
  obviously-bad cases (wrong signature, truncated/malformed structure,
  oversized) with a 422 the candidate sees immediately.
- `extract_pdf_text` — the actual per-page text extraction, called from
  the background job (app/jobs/resume_processing.py). Deliberately not
  run synchronously in the request path — extraction cost scales with
  page count/complexity in a way signature validation doesn't.

Neither function ever calls an LLM. "Prefer deterministic parsing before
involving an LLM" — pypdf only.
"""

import io
import re
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.core.exceptions import UnprocessableEntityError

# Below this many alphanumeric characters in the fully-extracted,
# whitespace-normalized text, we treat the PDF as having no meaningful
# text layer — i.e. scanned/image-only. Deliberately small: a one-line
# resume is implausible, but we'd rather under- than over-trigger OCR
# guidance on a real (if sparse) text resume.
MEANINGFUL_TEXT_MIN_CHARS = 40

# A header/footer candidate (identical first/last line across pages) must
# repeat on at least this fraction of pages to be stripped, so a
# genuinely short unique line on one page is never mistaken for one.
_REPEATED_LINE_MIN_FRACTION = 0.5


@dataclass(slots=True)
class PdfExtractionResult:
    page_texts: list[str]
    full_text: str
    page_count: int
    is_scanned: bool


def validate_pdf_upload(content: bytes, *, max_bytes: int) -> None:
    """Synchronous upload-time validation — magic bytes, trailer, size,
    and a real (if shallow) structural parse. Raises UnprocessableEntityError
    with a specific `code` for each distinct failure so clients can branch.
    """
    if not content:
        raise UnprocessableEntityError("Uploaded file is empty.", code="EMPTY_FILE")
    if len(content) > max_bytes:
        raise UnprocessableEntityError(
            f"File exceeds the maximum allowed size of {max_bytes // (1024 * 1024)}MB.",
            code="FILE_TOO_LARGE",
        )
    _validate_signature(content)
    _open_reader(content)  # raises MALFORMED_PDF on a bad object/xref structure


def extract_pdf_text(content: bytes) -> PdfExtractionResult:
    reader = _open_reader(content)
    raw_pages = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 — a single unparsable page must not fail the whole resume
            text = ""
        raw_pages.append(_normalize_whitespace(text))

    cleaned_pages = _strip_repeated_headers_footers(raw_pages)
    full_text = "\n\n".join(page for page in cleaned_pages if page).strip()
    meaningful_chars = sum(1 for ch in full_text if ch.isalnum())

    return PdfExtractionResult(
        page_texts=cleaned_pages,
        full_text=full_text,
        page_count=len(raw_pages),
        is_scanned=meaningful_chars < MEANINGFUL_TEXT_MIN_CHARS,
    )


def _validate_signature(content: bytes) -> None:
    if content[:5] != b"%PDF-":
        raise UnprocessableEntityError(
            "File does not have a valid PDF signature — the content does not "
            "match its extension/declared type.",
            code="INVALID_PDF_SIGNATURE",
        )
    if b"%%EOF" not in content[-2048:]:
        raise UnprocessableEntityError(
            "File is missing a valid PDF trailer (%%EOF) — it looks truncated or corrupted.",
            code="MALFORMED_PDF",
        )


def _open_reader(content: bytes) -> PdfReader:
    try:
        reader = PdfReader(io.BytesIO(content))
        _ = len(reader.pages)  # forces the page tree to actually be parsed
    except (PyPdfError, ValueError, KeyError, IndexError, TypeError) as exc:
        # PyPdfError is the base of every exception pypdf's own docs commit
        # to (PdfReadError, ParseError, DependencyError, ...) — narrower
        # PdfReadError alone misses ParseError/DependencyError, which are
        # PyPdfError direct subclasses, not PdfReadError ones. The
        # generic ValueError/KeyError/IndexError/TypeError entries catch
        # lower-level struct-unpacking failures pypdf doesn't wrap.
        raise UnprocessableEntityError(
            f"Uploaded file could not be parsed as a PDF: {exc}", code="MALFORMED_PDF"
        ) from exc
    if reader.is_encrypted:
        raise UnprocessableEntityError(
            "Password-protected PDFs are not supported.", code="ENCRYPTED_PDF"
        )
    return reader


def _normalize_whitespace(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    normalized = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", normalized).strip()


def _strip_repeated_headers_footers(pages: list[str]) -> list[str]:
    """Best-effort: drop a first/last line that repeats identically across
    a majority of pages (e.g. "Jane Doe — Resume" on every page footer).
    Only attempted for 3+ pages — below that, "repeated" isn't distinguishable
    from "coincidentally the same".
    """
    if len(pages) < 3:
        return pages

    first_lines = [_first_nonblank_line(page) for page in pages]
    last_lines = [_last_nonblank_line(page) for page in pages]
    header = _majority_repeated(first_lines, len(pages))
    footer = _majority_repeated(last_lines, len(pages))
    if header is None and footer is None:
        return pages

    stripped = []
    for page in pages:
        lines = page.splitlines()
        if lines and header and lines[0].strip().lower() == header:
            lines = lines[1:]
        if lines and footer and lines[-1].strip().lower() == footer:
            lines = lines[:-1]
        stripped.append("\n".join(lines).strip())
    return stripped


def _first_nonblank_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip().lower()
    return ""


def _last_nonblank_line(text: str) -> str:
    for line in reversed(text.splitlines()):
        if line.strip():
            return line.strip().lower()
    return ""


def _majority_repeated(values: list[str], page_count: int) -> str | None:
    counts: dict[str, int] = {}
    for value in values:
        if value:
            counts[value] = counts.get(value, 0) + 1
    threshold = max(2, int(page_count * _REPEATED_LINE_MIN_FRACTION) + 1)
    for value, count in counts.items():
        if count >= threshold:
            return value
    return None
