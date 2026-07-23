"""Current AVC Banner section availability for one course and term.

This is intentionally separate from the Knowledge Base and historical
offering-pattern data. Seat and waitlist values are read at tool-call time and
must never be treated as a registration guarantee.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from transfer_advisor.pipelines.banner_sections import (
    BASE_URL,
    BannerSession,
    get_terms,
    search_sections,
)

_COURSE_KEY = re.compile(r"^([A-Z]+)([0-9][A-Z0-9]*)$")
_TERM_CODE = re.compile(r"^\d{4}(10|30|50|70)$")
_VIEW_ONLY_SUFFIX = re.compile(r"\s*\(view only\)\s*$", re.IGNORECASE)


def _normalize_course_key(value: str) -> tuple[str, str]:
    normalized = re.sub(r"[\s-]+", "", value).upper()
    match = _COURSE_KEY.fullmatch(normalized)
    if match is None:
        raise ValueError(
            "course must contain an AVC subject and number, such as MATH 150"
        )
    return normalized, match.group(1)


def _normalize_term_label(value: str) -> str:
    return _VIEW_ONLY_SUFFIX.sub("", value).strip().casefold()


def _resolve_term(
    session: BannerSession,
    requested_term: str,
) -> tuple[str, str]:
    requested = requested_term.strip()
    terms = get_terms(session)
    by_code = {str(term["code"]): str(term["description"]) for term in terms}
    if _TERM_CODE.fullmatch(requested):
        if requested not in by_code:
            raise ValueError(f"Banner does not currently list term code {requested}.")
        return requested, by_code[requested]

    normalized = _normalize_term_label(requested)
    matches = [
        (code, description)
        for code, description in by_code.items()
        if _normalize_term_label(description) == normalized
    ]
    if len(matches) != 1:
        available = ", ".join(
            _VIEW_ONLY_SUFFIX.sub("", description)
            for description in list(by_code.values())[:8]
        )
        raise ValueError(
            f"Banner does not list a unique term matching {requested_term!r}. "
            f"Available recent terms include: {available}."
        )
    return matches[0]


def _meeting_times(section: dict[str, Any]) -> list[dict[str, Any]]:
    meetings = []
    for row in section.get("meetingsFaculty") or []:
        meeting = row.get("meetingTime") or {}
        meetings.append(
            {
                "begin_time": meeting.get("beginTime"),
                "end_time": meeting.get("endTime"),
                "days": [
                    day.title()
                    for day in (
                        "monday",
                        "tuesday",
                        "wednesday",
                        "thursday",
                        "friday",
                        "saturday",
                        "sunday",
                    )
                    if meeting.get(day)
                ],
                "start_date": meeting.get("startDate"),
                "end_date": meeting.get("endDate"),
                "building": meeting.get("buildingDescription"),
                "room": meeting.get("room"),
            }
        )
    return meetings


def _section_summary(section: dict[str, Any]) -> dict[str, Any]:
    return {
        "crn": section.get("courseReferenceNumber"),
        "section": section.get("sequenceNumber"),
        "title": section.get("courseTitle"),
        "campus": section.get("campusDescription"),
        "schedule_type": section.get("scheduleTypeDescription"),
        "instructional_method": section.get("instructionalMethodDescription"),
        "open_section": section.get("openSection"),
        "maximum_enrollment": section.get("maximumEnrollment"),
        "enrollment": section.get("enrollment"),
        "seats_available": section.get("seatsAvailable"),
        "wait_capacity": section.get("waitCapacity"),
        "wait_count": section.get("waitCount"),
        "wait_available": section.get("waitAvailable"),
        "cross_list_capacity": section.get("crossListCapacity"),
        "cross_list_count": section.get("crossListCount"),
        "cross_list_available": section.get("crossListAvailable"),
        "meetings": _meeting_times(section),
    }


def get_live_course_sections(
    *,
    course: str,
    term: str,
    session_factory: Callable[[], BannerSession] = BannerSession,
    checked_at: datetime | None = None,
) -> dict[str, Any]:
    """Return current Banner sections for exactly one AVC course and term."""
    course_key, subject = _normalize_course_key(course)
    session = session_factory()
    term_code, term_description = _resolve_term(session, term)
    session.register_term(term_code)
    rows = search_sections(session, subject, term_code)
    sections = [
        _section_summary(row)
        for row in rows
        if str(row.get("subjectCourse") or "").upper() == course_key
    ]
    timestamp = checked_at or datetime.now(UTC)
    return {
        "ok": True,
        "course": course_key,
        "term_code": term_code,
        "term_description": term_description,
        "checked_at": timestamp.astimezone(UTC).isoformat(),
        "sections": sections,
        "source": f"{BASE_URL}/classSearch/classSearch",
        "warning": (
            "Seat and waitlist counts can change immediately. Confirm the CRN "
            "and availability in AVC Banner before registering."
        ),
    }
