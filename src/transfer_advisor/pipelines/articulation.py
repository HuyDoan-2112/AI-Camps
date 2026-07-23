"""Flatten ASSIST agreement JSON into flat articulation rows -- Phase 2/3
(docs/architecture.md).

Turns the nested ASSIST agreement structure (data/raw/assist/*.json) into flat
rows -- the "articulation" structured-store table from Phase 3 -- with
`not_articulated` as a first-class status, never silently dropped.

ASSIST's sendingArticulation shape is an OR of AND-groups: the top-level `items`
list is alternative ways to satisfy the requirement (OR'd against each other);
each group's own `items` list is courses that must ALL be completed together
(AND'd within the group) -- e.g. "[MATH150] OR [MATH150H]" is two single-course
groups; "[MATH220 AND MATH230]" would be one two-course group. Represented here
as `sending_options: tuple[tuple[str, ...], ...]`.

Two receiving-side shapes exist in the raw data, both handled here:
  - `type: "Course"` -- one receiving course (the common case).
  - `type: "Series"` -- a *combined* multi-course receiving requirement (e.g.
    UCLA's "CHEM 20A, CHEM 20B, CHEM 20L" satisfied together). Same
    sendingArticulation shape as Course, just a different receiving-side label
    (`series["name"]` instead of a single course). Originally skipped entirely
    here -- a real bug, not a documented limitation: it silently dropped ~5 of
    12 ME-pathway target courses (PHYS110, PHYS120, CHEM110, ENGR210, MATH230)
    from get_courses_for_major() results because their only receiving-side
    match was a Series entry. Caught by testing against real data, not by
    inspection.
"""

from __future__ import annotations

from dataclasses import dataclass

from transfer_advisor.pipelines.normalize import normalize_course_key


@dataclass(frozen=True)
class ArticulationRow:
    major_key: str
    sending_institution_id: str
    receiving_institution_id: str
    academic_year: str
    receiving_course_key: str | None
    receiving_title: str | None
    status: str  # "articulated" | "not_articulated"
    sending_options: tuple[tuple[str, ...], ...]  # OR of AND-groups; empty if not_articulated
    reason: str | None  # populated for not_articulated


def flatten_agreement(
    agreement: dict,
    major_key: str,
    sending_institution_id: str,
    receiving_institution_id: str,
) -> list[ArticulationRow]:
    rows: list[ArticulationRow] = []
    academic_year = agreement["academicYear"]["code"]

    for entry in agreement.get("articulations", []):
        art = entry.get("articulation", {})
        entry_type = art.get("type")
        if entry_type not in ("Course", "Series"):
            continue

        if entry_type == "Course":
            course = art.get("course")
            receiving_key = (
                normalize_course_key(f"{course['prefix']}{course['courseNumber']}") if course else None
            )
            receiving_title = course["courseTitle"] if course else None
        else:  # Series -- no single receiving course_key, use the combined label
            series = art.get("series") or {}
            receiving_key = None
            receiving_title = series.get("name")

        sending = art.get("sendingArticulation", {})
        no_art_reason = sending.get("noArticulationReason")
        items = sending.get("items", [])

        if no_art_reason or not items:
            rows.append(
                ArticulationRow(
                    major_key=major_key,
                    sending_institution_id=sending_institution_id,
                    receiving_institution_id=receiving_institution_id,
                    academic_year=academic_year,
                    receiving_course_key=receiving_key,
                    receiving_title=receiving_title,
                    status="not_articulated",
                    sending_options=(),
                    reason=no_art_reason or "No sending courses listed",
                )
            )
            continue

        sending_options = tuple(
            tuple(
                normalize_course_key(f"{c['prefix']}{c['courseNumber']}") for c in group.get("items", [])
            )
            for group in items
        )
        rows.append(
            ArticulationRow(
                major_key=major_key,
                sending_institution_id=sending_institution_id,
                receiving_institution_id=receiving_institution_id,
                academic_year=academic_year,
                receiving_course_key=receiving_key,
                receiving_title=receiving_title,
                status="articulated",
                sending_options=sending_options,
                reason=None,
            )
        )

    return rows
