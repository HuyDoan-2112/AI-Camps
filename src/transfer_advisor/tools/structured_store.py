"""Reviewed structured-store lookups used by deterministic plan validation."""

from __future__ import annotations

import json

from transfer_advisor._project_root import project_root
from transfer_advisor.domain import (
    Course,
    GeArea,
    GeCourse,
    OfferingPattern,
    Prerequisites,
)

_ROOT = project_root()
_STORE_DIR = _ROOT / "data" / "processed" / "structured_store"

_courses_cache: dict[str, dict] | None = None
_offering_cache: dict[str, dict] | None = None
_prereq_cache: dict[str, dict] | None = None
_articulation_cache: list[dict] | None = None
_ge_cache: list[dict] | None = None


def _courses_raw() -> dict[str, dict]:
    global _courses_cache
    if _courses_cache is None:
        rows = json.loads((_STORE_DIR / "courses.json").read_text(encoding="utf-8"))
        _courses_cache = {r["course_key"]: r for r in rows}
    return _courses_cache


def _offering_raw() -> dict[str, dict]:
    global _offering_cache
    if _offering_cache is None:
        rows = json.loads((_STORE_DIR / "offering_pattern.json").read_text(encoding="utf-8"))
        _offering_cache = {r["course_key"]: r for r in rows}
    return _offering_cache


def _prereq_raw() -> dict[str, dict]:
    global _prereq_cache
    if _prereq_cache is None:
        payload = json.loads((_STORE_DIR / "prereq_graph.json").read_text(encoding="utf-8"))
        _prereq_cache = {c["course_key"]: c for c in payload["courses"]}
    return _prereq_cache


def _articulation_raw() -> list[dict]:
    global _articulation_cache
    if _articulation_cache is None:
        _articulation_cache = json.loads((_STORE_DIR / "articulation.json").read_text(encoding="utf-8"))
    return _articulation_cache


def _ge_raw() -> list[dict]:
    global _ge_cache
    if _ge_cache is None:
        _ge_cache = json.loads((_STORE_DIR / "ge_certification.json").read_text(encoding="utf-8"))
    return _ge_cache


def _build_offering_pattern(course_key: str) -> OfferingPattern:
    raw = _offering_raw()[course_key]
    return OfferingPattern(
        pattern_label=raw["pattern_label"],
        terms_observed=raw["terms_observed"],
        fall_count=raw["fall_count"],
        spring_count=raw["spring_count"],
        summer_count=raw["summer_count"],
        years_covered=raw["years_covered"],
    )


def _build_prerequisites(course_key: str) -> Prerequisites:
    raw = _prereq_raw().get(course_key)
    if raw is None:
        return Prerequisites()
    return Prerequisites(
        requires_all_of=tuple(raw["requires_all_of"]),
        requires_one_of=tuple(raw["requires_one_of"]),
        corequisite_of=tuple(raw["corequisite_of"]),
        advisory_only=tuple(raw["advisory_only"]),
    )


def get_all_courses() -> list[Course]:
    """All courses with reviewed prerequisite and offering facts."""
    courses = []
    for course_key, raw in _courses_raw().items():
        courses.append(
            Course(
                course_key=course_key,
                title=raw["title"],
                units=int(raw["units"]),
                prerequisites=_build_prerequisites(course_key),
                offering_pattern=_build_offering_pattern(course_key),
            )
        )
    return courses


def get_ge_courses(area_code: str | None = None) -> list[GeCourse]:
    """AVC courses currently certified for Cal-GETC. Unlike major articulation,
    this isn't keyed by (major, receiving institution) -- Cal-GETC is one
    system-wide pattern shared by UC and CSU (see
    pipelines/ge_certification.py). `area_code` filters to one Cal-GETC area
    (e.g. "3B"); omitted returns every certified course.
    """
    courses = [
        GeCourse(
            course_key=row["course_key"],
            title=row["title"],
            min_units=row["min_units"],
            max_units=row["max_units"],
            areas=tuple(GeArea(code=a["code"], description=a["description"]) for a in row["areas"]),
        )
        for row in _ge_raw()
    ]
    if area_code is None:
        return courses
    return [c for c in courses if any(a.code == area_code for a in c.areas)]


def get_articulation_rows(major_key: str) -> list[dict]:
    """Reviewed articulation rows, including not-articulated requirements."""
    return [row for row in _articulation_raw() if row["major_key"] == major_key]
