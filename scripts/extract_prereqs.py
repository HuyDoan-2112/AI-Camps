"""Fetch and parse real prerequisite text for the ME-pathway courses -- Phase 2
(docs/architecture.md).

Finds a real CRN per course from the Banner backfill, fetches its catalog
description live, and runs the conservative parser in
transfer_advisor.pipelines.prereq_extraction. Writes a DRAFT prereq graph to
data/processed/banner/prereq_graph_draft.json (gitignored) and prints a
review-ready report: raw text next to the parsed structure, with anything
ambiguous explicitly flagged.

This is NOT a reviewed prerequisite graph. Per docs/architecture.md's build-time
HITL gate, a human must review every edge before plan validation can trust it --
this script's job is only to make that review fast, not to skip it.

Usage:
    python3 scripts/extract_prereqs.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transfer_advisor.pipelines import (  # noqa: E402
    BannerSession,
    get_course_description,
    parse_course_description,
)

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "banner"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "banner" / "prereq_graph_draft.json"

# The ME-pathway courses confirmed for real against the ASSIST AVC->UCLA/CPP
# agreements earlier in this project. subject is needed to find the right raw file.
TARGET_COURSES = [
    ("MATH", "MATH150"),
    ("MATH", "MATH160"),
    ("MATH", "MATH250"),
    ("MATH", "MATH230"),
    ("MATH", "MATH220"),
    ("PHYS", "PHYS110"),
    ("PHYS", "PHYS120"),
    ("CHEM", "CHEM110"),
    ("ENGR", "ENGR210"),
    ("ENGR", "ENGR140"),
    ("ENGR", "ENGR110"),
    ("ENGR", "ENGR125"),
]

# Most recent terms first -- prefer a recent CRN, fall back if not offered.
PREFERRED_TERMS = ["202630", "202570", "202530", "202470"]


def _find_crn(subject: str, course_key: str) -> tuple[str, str] | None:
    for term_code in PREFERRED_TERMS:
        path = RAW_DIR / f"term={term_code}" / f"{subject}.json"
        if not path.exists():
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        row = next((r for r in rows if r["subjectCourse"] == course_key), None)
        if row:
            return term_code, row["courseReferenceNumber"]
    return None


def main() -> int:
    session = BannerSession()
    results = []
    review_flags = []

    for subject, course_key in TARGET_COURSES:
        found = _find_crn(subject, course_key)
        if not found:
            print(f"{course_key}: not found in any preferred term -- skipping")
            continue
        term_code, crn = found

        # Register the term before fetching -- given search_sections' server-side
        # session-state surprise (see banner_sections.py), don't assume
        # getCourseDescription is stateless just because term is a query param.
        session.register_term(term_code)
        raw_html = get_course_description(session, term_code, crn)
        parsed = parse_course_description(raw_html, course_key, term_code, crn)
        results.append(parsed)

        print(f"\n=== {course_key} (term={term_code} crn={crn}) ===")
        if not parsed.clauses:
            print("  (no Prerequisite/Corequisite/Advisory clause found)")
        for clause in parsed.clauses:
            flag = "  [NEEDS REVIEW: " + clause.review_reason + "]" if clause.needs_manual_review else ""
            print(f"  {clause.label}: \"{clause.raw_text}\"")
            print(f"    -> courses={clause.course_keys} conjunction={clause.conjunction}{flag}")
            if clause.needs_manual_review:
                review_flags.append((course_key, clause.label, clause.review_reason))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps([asdict(r) for r in results], indent=2), encoding="utf-8")
    print(f"\nWrote {len(results)} draft prerequisite records to {OUT_PATH}")

    print(f"\n{len(review_flags)} clauses flagged for manual review:")
    for course_key, label, reason in review_flags:
        print(f"  {course_key} ({label}): {reason}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
