"""Transcript parser tests -- v2 (docs/architecture.md).

Row fixtures below are hand-built to match real pdfplumber table output
shapes observed while building this (not a fixture PDF -- a real student's
transcript, even redacted, doesn't belong in version control). Course codes
here are generic AVC catalog codes, not tied to any person's record.
"""

import unittest

from transfer_advisor.pipelines.transcript_parser import _courses_from_rows, _extract_course_and_grade


class ExtractCourseAndGradeTest(unittest.TestCase):
    def test_normal_row(self) -> None:
        row = ["ENGL 101", "", "UG", "Freshman Co", "mposition", "C", "3.000", "6.00", "", "", "", ""]
        self.assertEqual(_extract_course_and_grade(row), ("ENGL101", "C"))

    def test_grade_glued_onto_title_with_zero_space(self) -> None:
        # Real bug found in a real transcript: "College and Life ManagementC"
        # -- pdfplumber's text-table strategy still separates it into cells.
        row = ["HD 101", "", "UG", "College and L", "ife Management", "C", "3.000", "6.00", "", "", "", ""]
        self.assertEqual(_extract_course_and_grade(row), ("HD101", "C"))

    def test_row_with_trailing_repeat_flag_still_finds_grade(self) -> None:
        row = ["PE 15R4", "", "UG ADV BASKE", "TBALL TECH", "A", "", "1.000", "4.00", "I", "", "", ""]
        self.assertEqual(_extract_course_and_grade(row), ("PE15R4", "A"))

    def test_withdrawal_grade_is_extracted_but_not_passing(self) -> None:
        row = ["PHYS 101", "", "UG", "Introductory", "Physics", "W", "3.000", "0.00", "", "", "", ""]
        self.assertEqual(_extract_course_and_grade(row), ("PHYS101", "W"))

    def test_course_code_without_space_still_splits(self) -> None:
        row = ["MATH C", "", "UG INT ALGEB", "RA", "A", "", "4.000", "16.00", "", "", "", ""]
        self.assertEqual(_extract_course_and_grade(row), ("MATHC", "A"))

    def test_section_header_row_returns_none(self) -> None:
        row = ["DEGREES AWARDED", "", "", "", "", "", "", "", "", "", "", ""]
        self.assertIsNone(_extract_course_and_grade(row))

    def test_term_totals_row_returns_none(self) -> None:
        # "Term"/"Current" aren't all-uppercase subject codes, so this is
        # rejected before the (misleading) decimal-shaped Attempt Hours cells
        # are ever considered.
        row = ["Current Term", "12.000", "", "9.000", "9.00", "0", "9.000", "", "", "18.00", "", "2.00"]
        self.assertIsNone(_extract_course_and_grade(row))

    def test_empty_row_returns_none(self) -> None:
        self.assertIsNone(_extract_course_and_grade(["", "", "", "", "", "", "", "", "", "", "", ""]))

    def test_row_with_no_credit_hours_cell_returns_none(self) -> None:
        row = ["Term: Spring 2001", "", "", "", "", "", "", "", "", "", "", ""]
        self.assertIsNone(_extract_course_and_grade(row))


class CoursesFromRowsTest(unittest.TestCase):
    def test_passing_grades_are_collected(self) -> None:
        rows = [
            ["MATH 150", "", "UG", "Calculus", "", "B", "5.000", "15.00", "", "", "", ""],
            ["CHEM 101", "", "UG", "Chemistry", "", "A", "4.000", "16.00", "", "", "", ""],
        ]
        self.assertEqual(_courses_from_rows(rows), {"MATH150", "CHEM101"})

    def test_failing_withdrawn_and_d_grades_are_excluded(self) -> None:
        rows = [
            ["MATH 150", "", "UG", "Calculus", "", "F", "5.000", "0.00", "", "", "", ""],
            ["MATH 150", "", "UG", "Calculus", "", "D", "5.000", "0.00", "", "", "", ""],
            ["PHYS 101", "", "UG", "Physics", "", "W", "3.000", "0.00", "", "", "", ""],
        ]
        self.assertEqual(_courses_from_rows(rows), set())

    def test_a_repeated_course_counts_if_any_attempt_passed(self) -> None:
        # Real finding: MATH150 attempted 4 times across terms with grades
        # F, D, C, B -- must count once it's ever passed, not be excluded
        # because an earlier attempt failed.
        rows = [
            ["MATH 150", "", "UG", "Calculus", "", "F", "5.000", "0.00", "", "", "", ""],
            ["MATH 150", "", "UG", "Calculus", "", "D", "5.000", "0.00", "", "", "", ""],
            ["MATH 150", "", "UG", "Calculus", "", "C", "5.000", "10.00", "", "", "", ""],
            ["MATH 150", "", "UG", "Calculus", "", "B", "5.000", "15.00", "", "", "", ""],
        ]
        self.assertEqual(_courses_from_rows(rows), {"MATH150"})

    def test_pass_no_pass_p_grade_counts_as_passing(self) -> None:
        rows = [["PE 150", "", "UG", "Fitness Swimming", "", "P", "1.000", "0.00", "", "", "", ""]]
        self.assertEqual(_courses_from_rows(rows), {"PE150"})

    def test_non_course_rows_are_ignored(self) -> None:
        rows = [
            ["STUDENT INFORMAT", "ION", "", "", "", "", "", "", "", "", "", ""],
            ["Term Totals", "Attempt", "Hours", "", "", "", "", "", "", "", "", ""],
            ["MATH 150", "", "UG", "Calculus", "", "B", "5.000", "15.00", "", "", "", ""],
        ]
        self.assertEqual(_courses_from_rows(rows), {"MATH150"})


if __name__ == "__main__":
    unittest.main()
