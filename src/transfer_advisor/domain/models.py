"""Typed course, prerequisite, offering, articulation, and GE source models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TermType = Literal["fall", "spring", "summer", "winter"]

OfferingLabel = Literal[
    "every_term",
    "fall_only",
    "spring_only",
    "alternating_years",
    "irregular",
    "discontinued",
    "insufficient_data",
]

@dataclass(frozen=True)
class Prerequisites:
    requires_all_of: tuple[str, ...] = ()
    requires_one_of: tuple[str, ...] = ()
    corequisite_of: tuple[str, ...] = ()
    advisory_only: tuple[str, ...] = ()


@dataclass(frozen=True)
class OfferingPattern:
    pattern_label: OfferingLabel
    terms_observed: int
    fall_count: int
    spring_count: int
    summer_count: int
    years_covered: int

    @property
    def is_reliable(self) -> bool:
        """False for patterns the assistant must hedge on rather than state plainly."""
        return self.pattern_label not in ("irregular", "insufficient_data")

    def permits(self, term_type: TermType) -> bool:
        """Whether this pattern allows scheduling the course in a term of this type.

        `irregular` and `insufficient_data` are intentionally permitted here --
        the caller is responsible for attaching a warning, not for hiding the
        course. Silently excluding it would be a different kind of wrong answer.
        """
        if self.pattern_label == "discontinued":
            return False
        if self.pattern_label == "fall_only":
            return term_type == "fall"
        if self.pattern_label == "spring_only":
            return term_type == "spring"
        return True


@dataclass(frozen=True)
class GeArea:
    code: str
    description: str


@dataclass(frozen=True)
class GeCourse:
    """One AVC course certified for Cal-GETC, and which area(s) it satisfies.

    Cal-GETC replaced the separate IGETC and CSU GE-Breadth patterns starting
    Fall 2025 -- a single, system-wide pattern shared by UC and CSU, not one
    per receiving institution the way major articulation is. See
    pipelines/ge_certification.py for the real ASSIST source."""

    course_key: str
    title: str
    min_units: float
    max_units: float
    areas: tuple[GeArea, ...]


@dataclass(frozen=True)
class Course:
    course_key: str
    title: str
    units: int
    prerequisites: Prerequisites
    offering_pattern: OfferingPattern
