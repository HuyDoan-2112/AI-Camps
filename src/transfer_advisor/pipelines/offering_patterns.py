"""Offering-pattern derivation -- Phase 1a-derived (docs/architecture.md).

Transforms raw Banner backfill data (data/raw/banner/term=<code>/<SUBJECT>.json) into a
per-course_key offering pattern: how often a course runs by term type, over how many
years, with an explicit pattern_label and the sample size behind it -- never a bare
claim. This is a build-time transform over already-fetched data, not a live API call.

Derivation rules (docs/architecture.md, "1a-derived. Offering pattern table"), applied
in this order:
  - insufficient_data -- fewer than 4 observed terms. Say this rather than guessing.
  - discontinued      -- not offered in the most recent 3 terms of the window, but
                          present earlier.
  - fall_only         -- offered in >=80% of observed fall terms and <=10% of spring terms.
  - spring_only       -- the mirror of fall_only.
  - every_term        -- offered in >=80% of both fall and spring terms.
  - alternating_years -- offered in roughly half of same-type terms.
  - irregular         -- anything else that doesn't fit a clean label above.

course_key comes straight from Banner's own `subjectCourse` field (e.g. "MATH150"),
which is already normalized (uppercase, no whitespace) -- no separate normalizer
needed for this step (that's Phase 2's job for joining across *sources*, not within
Banner's own data).

Extension beyond the plan's literal schema: AVC also runs short Intersession terms,
which the plan's table doesn't call out as a fourth bucket. Tracked here as
`winter_count` rather than silently dropped or folded into another bucket.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

_TERM_TYPE_BY_CODE_SUFFIX = {"70": "fall", "50": "summer", "30": "spring", "10": "winter"}


@dataclass(frozen=True)
class DerivedOfferingPattern:
    course_key: str
    subject: str
    pattern_label: str
    terms_observed: int
    fall_count: int
    spring_count: int
    summer_count: int
    winter_count: int
    years_covered: int
    last_offered_term: str
    sample_terms: tuple[str, ...]  # every term_code this course appeared in, for traceability


def parse_term_type(term_code: str) -> str:
    suffix = term_code[-2:]
    if suffix not in _TERM_TYPE_BY_CODE_SUFFIX:
        raise ValueError(f"Unrecognized term code suffix in {term_code!r}")
    return _TERM_TYPE_BY_CODE_SUFFIX[suffix]


def parse_calendar_year(term_code: str) -> int:
    return int(term_code[:4])


def load_backfill(raw_dir: Path) -> dict[str, dict[str, list[dict]]]:
    """Returns {term_code: {subject: [section rows]}} from data/raw/banner/."""
    result: dict[str, dict[str, list[dict]]] = {}
    for term_dir in sorted(raw_dir.glob("term=*")):
        term_code = term_dir.name.split("=", 1)[1]
        result[term_code] = {}
        for subject_file in sorted(term_dir.glob("*.json")):
            subject = subject_file.stem
            result[term_code][subject] = json.loads(subject_file.read_text(encoding="utf-8"))
    return result


def derive_offering_patterns(backfill: dict[str, dict[str, list[dict]]]) -> list[DerivedOfferingPattern]:
    """One row per course_key observed anywhere in the backfill window."""
    all_terms = sorted(backfill.keys())
    terms_observed = len(all_terms)
    recent_terms = set(sorted(all_terms, reverse=True)[:3])

    fall_terms_total = sum(1 for t in all_terms if parse_term_type(t) == "fall")
    spring_terms_total = sum(1 for t in all_terms if parse_term_type(t) == "spring")
    years_covered = len({parse_calendar_year(t) for t in all_terms})

    course_terms: dict[str, set[str]] = {}
    course_subject: dict[str, str] = {}
    for term_code, by_subject in backfill.items():
        for subject, rows in by_subject.items():
            for row in rows:
                course_key = row["subjectCourse"]
                course_terms.setdefault(course_key, set()).add(term_code)
                course_subject[course_key] = subject

    patterns: list[DerivedOfferingPattern] = []
    for course_key in sorted(course_terms):
        terms_set = course_terms[course_key]
        fall = sum(1 for t in terms_set if parse_term_type(t) == "fall")
        spring = sum(1 for t in terms_set if parse_term_type(t) == "spring")
        summer = sum(1 for t in terms_set if parse_term_type(t) == "summer")
        winter = sum(1 for t in terms_set if parse_term_type(t) == "winter")

        label = _classify(
            observed_count=len(terms_set),
            fall=fall,
            spring=spring,
            fall_total=fall_terms_total,
            spring_total=spring_terms_total,
            observed_in_recent=bool(terms_set & recent_terms),
        )

        patterns.append(
            DerivedOfferingPattern(
                course_key=course_key,
                subject=course_subject[course_key],
                pattern_label=label,
                terms_observed=terms_observed,
                fall_count=fall,
                spring_count=spring,
                summer_count=summer,
                winter_count=winter,
                years_covered=years_covered,
                last_offered_term=max(terms_set),
                sample_terms=tuple(sorted(terms_set)),
            )
        )
    return patterns


def _classify(
    *,
    observed_count: int,
    fall: int,
    spring: int,
    fall_total: int,
    spring_total: int,
    observed_in_recent: bool,
) -> str:
    if observed_count < 4:
        return "insufficient_data"
    if not observed_in_recent:
        return "discontinued"

    fall_ratio = fall / fall_total if fall_total else 0.0
    spring_ratio = spring / spring_total if spring_total else 0.0

    if fall_ratio >= 0.8 and spring_ratio <= 0.1:
        return "fall_only"
    if spring_ratio >= 0.8 and fall_ratio <= 0.1:
        return "spring_only"
    if fall_ratio >= 0.8 and spring_ratio >= 0.8:
        return "every_term"
    if 0.35 <= fall_ratio <= 0.65 or 0.35 <= spring_ratio <= 0.65:
        return "alternating_years"
    return "irregular"


def to_json(patterns: list[DerivedOfferingPattern]) -> str:
    return json.dumps([asdict(p) for p in patterns], indent=2)
