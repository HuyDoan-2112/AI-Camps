"""Current Banner availability is a live tool, not Knowledge Base content."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from transfer_advisor.tools.live_sections import get_live_course_sections


class _FakeBannerSession:
    def __init__(self) -> None:
        self.registered_term: str | None = None

    def get_json(self, path, params):
        if path.endswith("/getTerms"):
            return [
                {"code": "202670", "description": "Fall 2026 (View Only)"},
                {"code": "202650", "description": "Summer 2026"},
            ]
        if path.endswith("/searchResults"):
            return {
                "success": True,
                "totalCount": 2,
                "data": [
                    {
                        "subjectCourse": "MATH150",
                        "courseReferenceNumber": "12345",
                        "sequenceNumber": "01",
                        "courseTitle": "Calculus",
                        "campusDescription": "Lancaster Campus",
                        "scheduleTypeDescription": "Lecture",
                        "instructionalMethodDescription": "In Person",
                        "openSection": True,
                        "maximumEnrollment": 30,
                        "enrollment": 28,
                        "seatsAvailable": 2,
                        "waitCapacity": 5,
                        "waitCount": 1,
                        "waitAvailable": 4,
                        "meetingsFaculty": [],
                    },
                    {
                        "subjectCourse": "MATH160",
                        "courseReferenceNumber": "99999",
                    },
                ],
            }
        raise AssertionError((path, params))

    def register_term(self, term_code: str) -> None:
        self.registered_term = term_code

    def reset_search_form(self) -> None:
        return None


class LiveCourseSectionsTest(unittest.TestCase):
    def test_returns_only_requested_course_with_freshness_metadata(self) -> None:
        checked_at = datetime(2026, 7, 23, 18, 30, tzinfo=UTC)
        result = get_live_course_sections(
            course="MATH 150",
            term="Fall 2026",
            session_factory=_FakeBannerSession,
            checked_at=checked_at,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["course"], "MATH150")
        self.assertEqual(result["term_code"], "202670")
        self.assertEqual(result["checked_at"], "2026-07-23T18:30:00+00:00")
        self.assertEqual(len(result["sections"]), 1)
        self.assertEqual(result["sections"][0]["seats_available"], 2)
        self.assertEqual(result["sections"][0]["wait_count"], 1)
        self.assertIn("change immediately", result["warning"])

    def test_rejects_unrecognized_course_shape(self) -> None:
        with self.assertRaisesRegex(ValueError, "subject and number"):
            get_live_course_sections(
                course="calculus",
                term="Fall 2026",
                session_factory=_FakeBannerSession,
            )


if __name__ == "__main__":
    unittest.main()
