"""get_ge_courses() tests -- v2 (docs/architecture.md), against real data.

No existing test file covered tools/structured_store.py directly before this
(coverage came indirectly through test_router.py/test_real_data_pathway.py) --
this is new, first-class v2 functionality, so it gets its own direct tests
against the real Cal-GETC data fetched from ASSIST.
"""

import unittest

from transfer_advisor.tools.structured_store import get_ge_courses


class GeCoursesTest(unittest.TestCase):
    def test_returns_real_certified_courses(self) -> None:
        courses = get_ge_courses()
        self.assertGreater(len(courses), 100)  # 199 as of the 2025-26 fetch
        course_keys = {c.course_key for c in courses}
        self.assertIn("PSYCC1000", course_keys)  # renamed from PSY101 for Fall 2025 (CCN)
        self.assertIn("POLSC1000", course_keys)

    def test_every_course_has_at_least_one_area(self) -> None:
        for course in get_ge_courses():
            self.assertTrue(course.areas, f"{course.course_key} has no Cal-GETC areas")

    def test_area_code_filter_matches_unfiltered_subset(self) -> None:
        all_courses = get_ge_courses()
        area_4 = get_ge_courses(area_code="4")
        self.assertTrue(area_4)
        self.assertLess(len(area_4), len(all_courses))
        for course in area_4:
            self.assertTrue(any(a.code == "4" for a in course.areas))

    def test_unknown_area_code_returns_empty_not_error(self) -> None:
        self.assertEqual(get_ge_courses(area_code="nonexistent"), [])


if __name__ == "__main__":
    unittest.main()
