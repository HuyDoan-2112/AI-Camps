"""The deterministic validator checks model drafts; it never builds them."""

from __future__ import annotations

import unittest

from transfer_advisor.planning import validate_proposed_plan
from transfer_advisor.tools.structured_store import get_articulation_rows


def _major_courses(major: str) -> set[str]:
    return {
        course
        for row in get_articulation_rows(major)
        if row["status"] == "articulated"
        for option in row["sending_options"]
        for course in option
    }


def _one_known_option_per_requirement(major: str) -> set[str]:
    from transfer_advisor.tools.structured_store import get_all_courses, get_ge_courses

    known = {course.course_key for course in get_all_courses()} | {
        course.course_key for course in get_ge_courses()
    }
    selected: set[str] = set()
    for row in get_articulation_rows(major):
        if row["status"] != "articulated":
            continue
        option = next(
            (set(candidate) for candidate in row["sending_options"] if set(candidate) <= known),
            set(),
        )
        selected.update(option)
    return selected


class ValidateProposedPlanTest(unittest.TestCase):
    def test_accepts_exact_draft_when_supported_checks_pass(self) -> None:
        completed = _one_known_option_per_requirement("me_cpp") - {"ENGR110"}
        result = validate_proposed_plan(
            major="me_cpp",
            completed_courses=sorted(completed),
            terms=[
                {
                    "term": "Fall 2026",
                    "term_type": "fall",
                    "courses": ["ENGR110"],
                }
            ],
        )

        self.assertTrue(result["valid"], result["errors"])
        self.assertIn("Cal-GETC", result["destination_ge_policy"]["summary"])

    def test_rejects_invented_repeated_and_overloaded_courses(self) -> None:
        result = validate_proposed_plan(
            major="me_ucla",
            completed_courses=["MATH150"],
            max_units_per_term=8,
            max_stem_per_term=1,
            terms=[
                {
                    "term": "Spring 2026",
                    "term_type": "spring",
                    "courses": ["MATH150", "MATH160", "PHYS110", "FAKE999"],
                }
            ],
        )

        codes = {error["code"] for error in result["errors"]}
        self.assertFalse(result["valid"])
        self.assertIn("already_completed", codes)
        self.assertIn("unknown_course", codes)
        self.assertIn("above_student_unit_maximum", codes)
        self.assertIn("above_student_stem_maximum", codes)

    def test_requires_prerequisites_before_not_during_same_term(self) -> None:
        result = validate_proposed_plan(
            major="me_ucla",
            completed_courses=[],
            terms=[
                {
                    "term": "Fall 2026",
                    "term_type": "fall",
                    "courses": ["MATH150", "MATH160"],
                }
            ],
        )

        messages = [
            error["message"]
            for error in result["errors"]
            if error["code"].startswith("missing_prerequisite")
        ]
        self.assertTrue(any("MATH150 requires one of" in message for message in messages))
        self.assertTrue(any("MATH160 requires one of" in message for message in messages))

    def test_ge_matches_are_evidence_not_certification(self) -> None:
        completed = sorted(_major_courses("me_ucla") | {"COMMC1000", "ART100"})
        result = validate_proposed_plan(
            major="me_ucla",
            completed_courses=completed,
            terms=[
                {
                    "term": "Fall 2026",
                    "term_type": "fall",
                    "courses": ["COMMC1000"],
                }
            ],
        )

        self.assertIn("1C", result["ge_area_evidence"])
        warning_codes = {warning["code"] for warning in result["warnings"]}
        self.assertIn("ge_evidence_not_certification", warning_codes)


if __name__ == "__main__":
    unittest.main()
