"""AVC unofficial transcript PDF parsing -- v2 transcript upload
(docs/architecture.md).

Verified against a real AVC Banner self-service transcript export, not
guessed: `pdffonts` on a real download shows embedded, Unicode-mapped
TrueType fonts, confirming this is a native text-layer PDF, not a scan --
so no OCR service is needed for the format every AVC student downloads. If
a photographed/scanned transcript ever needs support, Amazon Textract's
AnalyzeDocument (TABLES feature) is the right AWS service for that --
deliberately not built here since it's unneeded for this format.

Grades are extracted only long enough to apply the pass/fail filter below,
then discarded -- nothing about a student's grades is returned, stored, or
logged; only the resulting set of passed course keys survives this module.
Per AVC's own stated policy: C or better (or Pass, for Pass/No-Pass
courses) counts as passing. A D earns credit hours but does not satisfy a
prerequisite, major, or transfer requirement, so it is NOT treated as
passing here. "CR" (credit, used by some cr/no-cr schemes) is deliberately
left out of PASSING_GRADES -- not confirmed against AVC's policy, and no
real row in the transcript this was built against used it; a false
"not completed" is a safe default, a false "completed" is not.

Column extraction uses pdfplumber's borderless-table strategy
(vertical/horizontal_strategy="text") rather than a fixed column index --
verified necessary against a real row where the grade letter is glued
directly onto the title with zero space ("College and Life ManagementC"),
which breaks whitespace- or regex-based parsing. The Grade cell itself is
identified by position relative to the Credit Hours cell (always shaped
like `\\d+\\.\\d{3}`, e.g. "3.000"), not by a fixed column index, since the
text-based table strategy infers slightly different column boundaries per
page depending on that page's own content.
"""

from __future__ import annotations

import io
import re

PASSING_GRADES = frozenset({"A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "P"})

_KNOWN_GRADE_CODES = PASSING_GRADES | frozenset(
    {"D+", "D", "D-", "F", "W", "NP", "NC", "I", "IP", "AU"}
)

_CREDIT_HOURS_PATTERN = re.compile(r"^\d+\.\d{3}$")
_SUBJECT_PATTERN = re.compile(r"^[A-Z]{1,5}$")

_TABLE_SETTINGS = {"vertical_strategy": "text", "horizontal_strategy": "text"}

# Below this much extracted text across the whole PDF, treat it as a
# scanned/image-only document (no text layer) rather than a real transcript.
_MIN_TEXT_LAYER_CHARS = 100


class ScannedPdfError(Exception):
    """Raised when a PDF has no usable text layer (likely scanned/photographed),
    so text extraction can't work and OCR would be required."""


def parse_transcript(pdf_bytes: bytes) -> set[str]:
    """Returns the set of course keys (e.g. "MATH150") the student has
    passed, per AVC's C-or-better policy. A course repeated with multiple
    grades counts if ANY attempt passed."""
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pdfplumber is required to parse transcript PDFs -- pip install pdfplumber") from exc

    rows: list[list[str | None]] = []
    extracted_text_len = 0
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            extracted_text_len += len((page.extract_text() or "").strip())
            for table in page.extract_tables(_TABLE_SETTINGS):
                rows.extend(table)

    # A scanned/photographed transcript is an image with no text layer, so
    # pdfplumber pulls essentially nothing. Distinguish that from a real
    # text-layer PDF that simply had no passing rows -- the caller shows a very
    # different message ("this looks scanned, needs OCR" vs "no passing
    # courses found"). Threshold is deliberately low: even a one-page real
    # transcript yields thousands of characters.
    if extracted_text_len < _MIN_TEXT_LAYER_CHARS:
        raise ScannedPdfError(
            "This PDF has no readable text layer -- it looks scanned or photographed. "
            "Download the official text version from AVC's Banner self-service, or enable OCR."
        )

    return _courses_from_rows(rows)


def _courses_from_rows(rows: list[list[str | None]]) -> set[str]:
    completed: set[str] = set()
    for row in rows:
        parsed = _extract_course_and_grade(row)
        if parsed is None:
            continue
        course_key, grade = parsed
        if grade in PASSING_GRADES:
            completed.add(course_key)
    return completed


def _extract_course_and_grade(cells: list[str | None]) -> tuple[str, str] | None:
    """Pure row parser -- no pdfplumber/IO dependency, so it's directly
    unit-testable against hand-built row shapes taken from real transcript
    output."""
    if not cells or not cells[0]:
        return None

    head = cells[0].split(maxsplit=1)
    if len(head) < 2:
        return None
    subject, course = head[0], head[1].replace(" ", "")
    if not _SUBJECT_PATTERN.match(subject):
        return None

    credit_idx = next(
        (i for i, cell in enumerate(cells) if cell and _CREDIT_HOURS_PATTERN.match(cell.strip())),
        None,
    )
    if credit_idx is None:
        return None

    candidates = [cell.strip() for cell in cells[:credit_idx] if cell and cell.strip()]
    if not candidates:
        return None
    grade = candidates[-1]
    if grade not in _KNOWN_GRADE_CODES:
        return None

    course_key = f"{subject}{course}".upper()
    return course_key, grade
