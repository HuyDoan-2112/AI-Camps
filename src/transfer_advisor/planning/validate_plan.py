"""Validate a model-proposed transfer plan without designing one.

The managed AgentCore Harness owns the interview and planning decisions. This
module is deliberately limited to factual checks over the reviewed structured
store: it never selects courses, moves courses, or invents a term sequence.
"""

from __future__ import annotations

import csv
from typing import Any

from transfer_advisor._project_root import project_root
from transfer_advisor.tools.structured_store import (
    get_all_courses,
    get_articulation_rows,
    get_ge_courses,
)

_VALID_TERM_TYPES = {"fall", "spring", "summer", "winter"}
_HEDGE_PATTERNS = {"alternating_years", "irregular", "insufficient_data"}


def _normalize_course_key(value: str) -> str:
    return "".join(value.upper().split())


def _configured_major(major_key: str) -> dict[str, str] | None:
    path = project_root() / "config" / "majors.csv"
    with path.open(newline="", encoding="utf-8") as file:
        return next(
            (row for row in csv.DictReader(file) if row["major_key"] == major_key),
            None,
        )


def _destination_ge_policy(institution_id: str) -> dict[str, str] | None:
    path = project_root() / "config" / "transfer_ge_policies.csv"
    with path.open(newline="", encoding="utf-8") as file:
        row = next(
            (
                candidate
                for candidate in csv.DictReader(file)
                if candidate["institution_id"] == institution_id
                and candidate["program_scope"] == "engineering"
            ),
            None,
        )
    if row is None:
        return None
    return {
        "academic_year": row["academic_year"],
        "summary": row["policy_summary"],
        "source_url": row["source_url"],
        "verified_on": row["verified_on"],
    }


def validate_proposed_plan(
    *,
    major: str,
    completed_courses: list[str],
    terms: list[dict[str, Any]],
    min_units_per_term: float | None = None,
    max_units_per_term: float | None = None,
    max_stem_per_term: int | None = None,
) -> dict[str, Any]:
    """Return factual validation findings for an exact model-proposed plan.

    ``terms`` must contain ``term`` (a display label), ``term_type`` and a list
    of AVC ``courses``. A successful result means only that checks supported by
    the current reviewed data passed; it is not an admission or seat guarantee.
    """
    major_row = _configured_major(major)
    if major_row is None:
        return {
            "valid": False,
            "errors": [
                {
                    "code": "unknown_major",
                    "message": f"Unknown configured major: {major}",
                }
            ],
            "warnings": [],
        }

    course_rows = {course.course_key: course for course in get_all_courses()}
    ge_rows = {course.course_key: course for course in get_ge_courses()}
    known_course_keys = set(course_rows) | set(ge_rows)
    articulation_rows = get_articulation_rows(major)
    major_course_keys = {
        course_key
        for row in articulation_rows
        if row["status"] == "articulated"
        for option in row.get("sending_options", [])
        for course_key in option
    }

    completed = {_normalize_course_key(key) for key in completed_courses}
    previously_available = set(completed)
    scheduled: set[str] = set()
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    term_summaries: list[dict[str, Any]] = []

    if not terms:
        errors.append({"code": "empty_plan", "message": "The proposed plan has no terms."})

    for term_index, term in enumerate(terms):
        label = str(term.get("term") or f"Term {term_index + 1}")
        term_type = str(term.get("term_type") or "").strip().lower()
        raw_courses = term.get("courses")
        if term_type not in _VALID_TERM_TYPES:
            errors.append(
                {
                    "code": "invalid_term_type",
                    "term": label,
                    "message": (
                        f"{label} must declare fall, spring, summer, or winter."
                    ),
                }
            )
        if not isinstance(raw_courses, list):
            errors.append(
                {
                    "code": "invalid_courses",
                    "term": label,
                    "message": f"{label} courses must be a list.",
                }
            )
            raw_courses = []

        keys = [_normalize_course_key(str(key)) for key in raw_courses]
        key_set = set(keys)
        term_units = 0.0
        stem_count = 0

        if len(keys) != len(key_set):
            errors.append(
                {
                    "code": "duplicate_within_term",
                    "term": label,
                    "message": f"{label} contains a duplicate course.",
                }
            )

        for key in keys:
            if key not in known_course_keys:
                errors.append(
                    {
                        "code": "unknown_course",
                        "term": label,
                        "course": key,
                        "message": f"{key} is not in the reviewed AVC course data.",
                    }
                )
                continue
            if key in completed:
                errors.append(
                    {
                        "code": "already_completed",
                        "term": label,
                        "course": key,
                        "message": f"{key} was reported completed but is scheduled again.",
                    }
                )
            if key in scheduled:
                errors.append(
                    {
                        "code": "duplicate_across_terms",
                        "term": label,
                        "course": key,
                        "message": f"{key} is scheduled more than once.",
                    }
                )

            if key in course_rows:
                course = course_rows[key]
                term_units += float(course.units)
                if key in major_course_keys:
                    stem_count += 1

                prereqs = course.prerequisites
                missing_all = sorted(set(prereqs.requires_all_of) - previously_available)
                if missing_all:
                    errors.append(
                        {
                            "code": "missing_prerequisite",
                            "term": label,
                            "course": key,
                            "message": f"{key} requires {', '.join(missing_all)} first.",
                        }
                    )
                alternatives = set(prereqs.requires_one_of)
                if alternatives and not alternatives.intersection(previously_available):
                    errors.append(
                        {
                            "code": "missing_prerequisite_option",
                            "term": label,
                            "course": key,
                            "message": (
                                f"{key} requires one of "
                                f"{'/'.join(sorted(alternatives))} first."
                            ),
                        }
                    )
                missing_coreqs = sorted(
                    set(prereqs.corequisite_of) - (previously_available | key_set)
                )
                if missing_coreqs:
                    errors.append(
                        {
                            "code": "missing_corequisite",
                            "term": label,
                            "course": key,
                            "message": (
                                f"{key} requires {', '.join(missing_coreqs)} "
                                "before or in the same term."
                            ),
                        }
                    )

                pattern = course.offering_pattern
                if term_type in _VALID_TERM_TYPES and not pattern.permits(term_type):
                    errors.append(
                        {
                            "code": "offering_mismatch",
                            "term": label,
                            "course": key,
                            "message": (
                                f"{key}'s reviewed historical pattern "
                                f"({pattern.pattern_label}) does not support {term_type}."
                            ),
                        }
                    )
                elif pattern.pattern_label in _HEDGE_PATTERNS:
                    warnings.append(
                        {
                            "code": "uncertain_offering",
                            "term": label,
                            "course": key,
                            "message": (
                                f"{key} has a {pattern.pattern_label} historical "
                                "offering pattern; confirm the future section."
                            ),
                        }
                    )
            else:
                ge_course = ge_rows[key]
                term_units += float(ge_course.max_units or ge_course.min_units)

        if min_units_per_term is not None and term_units < min_units_per_term:
            errors.append(
                {
                    "code": "below_student_unit_minimum",
                    "term": label,
                    "message": (
                        f"{label} has {term_units:g} known units, below the "
                        f"student's {min_units_per_term:g}-unit minimum."
                    ),
                }
            )
        if max_units_per_term is not None and term_units > max_units_per_term:
            errors.append(
                {
                    "code": "above_student_unit_maximum",
                    "term": label,
                    "message": (
                        f"{label} has {term_units:g} known units, above the "
                        f"student's {max_units_per_term:g}-unit maximum."
                    ),
                }
            )
        if max_stem_per_term is not None and stem_count > max_stem_per_term:
            errors.append(
                {
                    "code": "above_student_stem_maximum",
                    "term": label,
                    "message": (
                        f"{label} has {stem_count} major-preparation courses, above "
                        f"the student's maximum of {max_stem_per_term}."
                    ),
                }
            )

        term_summaries.append(
            {
                "term": label,
                "term_type": term_type,
                "courses": keys,
                "known_units": term_units,
                "major_prep_course_count": stem_count,
            }
        )
        previously_available.update(key_set)
        scheduled.update(key_set)

    all_taken = completed | scheduled
    verified_taken = all_taken & known_course_keys
    requirement_coverage = []
    for row in articulation_rows:
        options = row.get("sending_options", [])
        satisfied = row["status"] == "articulated" and any(
            set(option).issubset(verified_taken) for option in options
        )
        requirement_coverage.append(
            {
                "receiving_course": row.get("receiving_course_key"),
                "receiving_title": row.get("receiving_title"),
                "status": row["status"],
                "satisfied_by_plan": satisfied,
                "sending_options": options,
                "reason": row.get("reason"),
            }
        )
        if row["status"] == "articulated" and not satisfied:
            errors.append(
                {
                    "code": "missing_articulated_requirement",
                    "receiving_course": row.get("receiving_course_key"),
                    "message": (
                        "The plan does not cover "
                        f"{row.get('receiving_course_key') or row.get('receiving_title')}."
                    ),
                }
            )

    ge_area_evidence: dict[str, list[str]] = {}
    for course in get_ge_courses():
        if course.course_key not in verified_taken:
            continue
        for area in course.areas:
            ge_area_evidence.setdefault(area.code, []).append(course.course_key)

    if completed - known_course_keys:
        warnings.append(
            {
                "code": "unverified_completed_courses",
                "courses": sorted(completed - known_course_keys),
                "message": (
                    "Some reported completed courses are outside the current reviewed "
                    "store and were not used to prove requirements."
                ),
            }
        )

    warnings.extend(
        [
            {
                "code": "future_sections_not_guaranteed",
                "message": (
                    "Offering checks use historical patterns and do not guarantee a "
                    "future section or seat."
                ),
            },
            {
                "code": "ge_evidence_not_certification",
                "message": (
                    "GE area matches are evidence only; they do not certify complete "
                    "Cal-GETC or destination graduation requirements."
                ),
            },
        ]
    )

    return {
        "valid": not errors,
        "major": major,
        "student_constraints": {
            "min_units_per_term": min_units_per_term,
            "max_units_per_term": max_units_per_term,
            "max_stem_per_term": max_stem_per_term,
        },
        "terms": term_summaries,
        "errors": errors,
        "warnings": warnings,
        "requirement_coverage": requirement_coverage,
        "ge_area_evidence": {
            area: sorted(course_keys)
            for area, course_keys in sorted(ge_area_evidence.items())
        },
        "destination_ge_policy": _destination_ge_policy(
            major_row["institution_id"]
        ),
    }
