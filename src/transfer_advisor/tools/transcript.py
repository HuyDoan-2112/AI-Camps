"""Transcript upload tool, wired for the API layer -- v2 (docs/architecture.md).

Parses whatever PDF bytes the client uploads. Malformed PDFs, non-transcript
PDFs, or a transcript with zero passing rows all surface as a caught
TranscriptParseError, never a raw crash -- matching this project's
never-crash-on-untrusted-input discipline used by the managed agent boundary.
"""

from __future__ import annotations

from transfer_advisor.pipelines.transcript_parser import ScannedPdfError, parse_transcript


class TranscriptParseError(Exception):
    """Raised when a transcript PDF can't be read, or yields no passing courses."""


def parse_transcript_upload(pdf_bytes: bytes) -> set[str]:
    """Returns the set of passed course keys. Does not touch session state --
    the caller decides whether/how to merge this into completed_courses."""
    try:
        completed = parse_transcript(pdf_bytes)
    except ScannedPdfError as exc:
        # Already a clear, user-facing message -- pass it through unwrapped.
        raise TranscriptParseError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 -- any parse failure, deliberately broad
        raise TranscriptParseError(f"Couldn't read this transcript PDF: {exc}") from exc
    if not completed:
        raise TranscriptParseError("No passing course rows were found in this transcript PDF.")
    return completed
