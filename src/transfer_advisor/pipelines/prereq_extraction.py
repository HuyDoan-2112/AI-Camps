"""Prerequisite-text extraction -- Phase 2 (docs/architecture.md).

Parses the raw HTML fragment from banner_sections.get_course_description() into a
best-effort structured guess at requires_all_of / requires_one_of / corequisite_of /
advisory_only -- deliberately conservative. Prerequisite prose is written for
humans and is genuinely ambiguous in places; where this parser can't confidently
classify a clause, it flags `needs_manual_review=True` and keeps the raw text
rather than guess. Per the plan's build-time HITL gate, EVERY edge this produces
still needs a human to review before plan validation can trust it -- nothing here is
self-certifying.

Real response shape this was built against (found by inspecting raw responses,
not documented anywhere): each labeled clause (Prerequisite:/Corequisite:/
Advisory:) occupies exactly one line, however many sentences it contains. The
general course-description prose always starts on the first line that doesn't
begin with a recognized label -- that's the parse boundary used here.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from transfer_advisor.pipelines.normalize import normalize_course_key

_TAG_OR_COMMENT = re.compile(r"<!--.*?-->|<[^>]+>", re.DOTALL)
_LABEL_LINE = re.compile(
    r"^(Prerequisites?(?:/Corequisites?)?|Corequisites?|Advisor(?:y|ies)):\s*(.*)$",
    re.IGNORECASE,
)
_COURSE_MENTION = re.compile(r"\b([A-Z]{2,5})\s+(\d{1,3}[A-Z]?)\b")
_PLACEMENT_ALTERNATIVE = re.compile(r"placement (?:by multiple measures|test)", re.IGNORECASE)
_CONCURRENT_ENROLLMENT = re.compile(r"concurrent enrollment", re.IGNORECASE)


@dataclass
class ExtractedClause:
    label: str  # "Prerequisite" | "Corequisite" | "Advisory"
    raw_text: str
    course_keys: tuple[str, ...] = ()
    conjunction: str | None = None  # "and" | "or" | None (single course or unparsed)
    has_placement_alternative: bool = False
    needs_manual_review: bool = False
    review_reason: str = ""


@dataclass
class ExtractedPrerequisites:
    course_key: str
    source_term: str
    source_crn: str
    raw_description: str
    clauses: list[ExtractedClause] = field(default_factory=list)
    reviewed: bool = False  # always False from extraction; a human flips this, not code


def _clean_lines(raw_html: str) -> list[str]:
    text = html.unescape(_TAG_OR_COMMENT.sub("", raw_html))
    return [line.strip() for line in text.split("\n") if line.strip()]


def _course_mention_matches(text: str) -> list[re.Match]:
    return list(_COURSE_MENTION.finditer(text))


def _extract_course_keys(matches: list[re.Match]) -> tuple[str, ...]:
    return tuple(normalize_course_key(f"{m.group(1)}{m.group(2)}") for m in matches)


def _spans_sentence_boundary(text: str, matches: list[re.Match]) -> bool:
    """True if a '.' appears between two consecutive course mentions -- a strong
    signal they're in separate sentences, not options joined by and/or. This is
    what catches cases like "Completion of PHYS 110. Completion of or concurrent
    enrollment in MATH 160." -- naive whole-clause word search sees "or" (from
    the "of or concurrent enrollment" idiom) and would otherwise wrongly conclude
    "PHYS110 or MATH160", when the real relationship is two separate sentences.
    """
    return any("." in text[a.end() : b.start()] for a, b in zip(matches, matches[1:]))


def _classify_conjunction(text: str, matches: list[re.Match]) -> tuple[str | None, bool, str]:
    """Returns (conjunction, needs_manual_review, reason)."""
    if len(matches) <= 1:
        return None, False, ""

    if _spans_sentence_boundary(text, matches):
        return (
            None,
            True,
            "course mentions span a sentence boundary (period) -- and/or word-presence "
            "can't reliably tell their relationship apart; read raw_text",
        )

    has_and = re.search(r"\band\b", text, re.IGNORECASE) is not None
    has_or = re.search(r"\bor\b", text, re.IGNORECASE) is not None

    if has_and and has_or:
        return None, True, "mixed 'and'/'or' in one clause -- logical grouping is ambiguous, do not guess"
    if has_and:
        return "and", False, ""
    if has_or:
        return "or", False, ""
    return None, True, "multiple courses mentioned with no recognized conjunction"


def parse_course_description(
    raw_html: str, course_key: str, source_term: str, source_crn: str
) -> ExtractedPrerequisites:
    lines = _clean_lines(raw_html)
    clauses: list[ExtractedClause] = []

    for line in lines:
        match = _LABEL_LINE.match(line)
        if not match:
            break  # first unlabeled line is the start of the general description

        label_raw, clause_text = match.group(1), match.group(2)
        label = "Prerequisite" if "prerequisite" in label_raw.lower() else label_raw.capitalize()
        if label_raw.lower().startswith("corequisite"):
            label = "Corequisite"
        elif label_raw.lower().startswith("advisor"):
            label = "Advisory"

        mentions = _course_mention_matches(clause_text)
        course_keys = _extract_course_keys(mentions)
        conjunction, needs_review, reason = _classify_conjunction(clause_text, mentions)
        has_placement = bool(_PLACEMENT_ALTERNATIVE.search(clause_text))

        if has_placement and not needs_review:
            # A non-course alternative exists alongside real courses -- fine to
            # keep the course_keys as an "or" group, but flag for review anyway
            # since "or placement" changes what counts as satisfied.
            needs_review = True
            reason = "includes a non-course alternative ('placement by multiple measures') alongside real courses"

        if not course_keys and not has_placement:
            needs_review = True
            reason = reason or "no recognizable course mentions in a labeled clause"

        clauses.append(
            ExtractedClause(
                label=label,
                raw_text=clause_text,
                course_keys=course_keys,
                conjunction=conjunction,
                has_placement_alternative=has_placement,
                needs_manual_review=needs_review,
                review_reason=reason,
            )
        )

    # "Completion of or concurrent enrollment in X" -- X can be taken the same
    # term, not strictly before. Re-tag as Corequisite so it doesn't get treated
    # as a hard prior-term block.
    for clause in clauses:
        if clause.label == "Prerequisite" and _CONCURRENT_ENROLLMENT.search(clause.raw_text):
            clause.label = "Corequisite"
            clause.needs_manual_review = True
            clause.review_reason = (
                clause.review_reason
                or "reclassified Prerequisite -> Corequisite due to 'concurrent enrollment' wording -- confirm this is right"
            )

    description = "\n".join(lines)
    return ExtractedPrerequisites(
        course_key=course_key,
        source_term=source_term,
        source_crn=source_crn,
        raw_description=description,
        clauses=clauses,
    )
