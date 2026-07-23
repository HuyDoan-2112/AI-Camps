"""Cal-GETC certification extraction -- v2 (docs/architecture.md's "GE is
cheaper than it looks" note).

Flattens one ASSIST /api/transferability/courses response
(pipelines/assist_seed.get_ge_certification_courses) into per-course GE area
coverage. Cal-GETC is a single, system-wide pattern shared by UC and CSU --
replaced the separate IGETC and CSU GE-Breadth patterns starting Fall 2025,
confirmed against real AVC data (courses show notations like "(Formerly PSY
101 prior to F2025)" and area entries literally named "Cal-GETC" alongside
now-superseded "IGETC"/"CSUGE" entries on the same row). So unlike major
articulation, this is one lookup per sending institution, not one per
(major, receiving institution) pair -- exactly the "two patterns, now one"
simplification the plan's note anticipated, just even more so than it guessed.
"""

from __future__ import annotations

from typing import Any

from transfer_advisor.domain.models import GeArea, GeCourse
from transfer_advisor.pipelines.normalize import normalize_course_key

PATTERN_NAME = "Cal-GETC"


def flatten_ge_certification(raw: dict[str, Any]) -> list[GeCourse]:
    """Filters to currently-active Cal-GETC area assignments only.

    ASSIST returns every pattern's full historical area assignments on every
    course row regardless of which `listType` was queried in the request --
    areas belonging to other patterns (IGETC, CSUGE) show up mixed in on the
    same row, filtered out here by requiring `name == "Cal-GETC"`.

    Deliberately does NOT also filter on the course row's own top-level
    `endTermCode` -- found the hard way: a real currently-certified course
    (ENGL C1000, satisfying Area 1A, English Composition) has a populated
    row-level `endTermCode` ("F2026") that looked like "discontinued," while
    its own nested Cal-GETC area entry has `endTermCode: ""` (genuinely
    indefinite). The row-level date reflects a periodic catalog-record
    renewal, not a real end of certification -- filtering on it silently
    dropped Area 1A (English Composition) from the entire certified list.
    Since Cal-GETC didn't exist before Fall 2025, no course can have a
    Cal-GETC-named area entry at all unless it's a current one -- the
    per-area `endTermCode` check below is sufficient on its own.
    """
    courses: list[GeCourse] = []
    for row in raw.get("courseInformationList", []):
        areas = tuple(
            GeArea(code=area["code"].strip(), description=area["codeDescription"].strip())
            for area in row.get("transferAreas", [])
            if area.get("name") == PATTERN_NAME and not area.get("endTermCode")
        )
        if not areas:
            continue  # e.g. still has an active IGETC/CSUGE area but not Cal-GETC

        courses.append(
            GeCourse(
                course_key=normalize_course_key(row["identifier"]),
                title=row["courseTitle"],
                min_units=row["minUnits"],
                max_units=row["maxUnits"],
                areas=areas,
            )
        )
    return courses
