"""tools/transcript.py tests -- v2 (docs/architecture.md)."""

import unittest
from unittest.mock import patch

from transfer_advisor.tools.transcript import TranscriptParseError, parse_transcript_upload


class ParseTranscriptUploadTest(unittest.TestCase):
    def test_returns_completed_courses_on_success(self) -> None:
        with patch(
            "transfer_advisor.tools.transcript.parse_transcript",
            return_value={"MATH150", "PHYS110"},
        ):
            self.assertEqual(parse_transcript_upload(b"fake pdf bytes"), {"MATH150", "PHYS110"})

    def test_raises_when_no_passing_courses_found(self) -> None:
        with patch("transfer_advisor.tools.transcript.parse_transcript", return_value=set()):
            with self.assertRaises(TranscriptParseError):
                parse_transcript_upload(b"fake pdf bytes")

    def test_raises_on_unparseable_pdf(self) -> None:
        with patch(
            "transfer_advisor.tools.transcript.parse_transcript",
            side_effect=RuntimeError("not a PDF"),
        ):
            with self.assertRaises(TranscriptParseError):
                parse_transcript_upload(b"not actually a pdf")

    def test_scanned_pdf_message_passes_through_clearly(self) -> None:
        # A scanned/image PDF must yield the "looks scanned / needs OCR"
        # message, not the misleading "no passing courses found" one.
        from transfer_advisor.pipelines.transcript_parser import ScannedPdfError

        with patch(
            "transfer_advisor.tools.transcript.parse_transcript",
            side_effect=ScannedPdfError("This PDF has no readable text layer -- it looks scanned or photographed."),
        ):
            with self.assertRaises(TranscriptParseError) as ctx:
                parse_transcript_upload(b"image-only pdf")
        self.assertIn("scanned", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
