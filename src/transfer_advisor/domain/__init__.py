"""Typed source and result models with no AWS dependencies."""

from transfer_advisor.domain.models import (
    Course,
    GeArea,
    GeCourse,
    OfferingLabel,
    OfferingPattern,
    Prerequisites,
    TermType,
)

__all__ = [
    "Course",
    "GeArea",
    "GeCourse",
    "OfferingLabel",
    "OfferingPattern",
    "Prerequisites",
    "TermType",
]
