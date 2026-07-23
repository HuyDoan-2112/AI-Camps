"""Build the published exact-data store used by the Streamlit tools.

Consolidates fetched, derived, and reviewed facts used by retrieval validation:
articulation, offerings, prerequisites, courses, and Cal-GETC certification.
Written to ``data/processed/structured_store/`` as small, versioned JSON files.

This does not touch AWS. See ``infra/README.md`` for publication.

Usage:
    python3 scripts/build_structured_store.py
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transfer_advisor.pipelines import flatten_agreement  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
ASSIST_DIR = ROOT / "data" / "raw" / "assist"
BANNER_DIR = ROOT / "data" / "raw" / "banner"
PROCESSED_DIR = ROOT / "data" / "processed"
OUT_DIR = PROCESSED_DIR / "structured_store"

TARGET_COURSES = [
    "MATH150", "MATH160", "MATH250", "MATH230", "MATH220",
    "PHYS110", "PHYS120", "CHEM110", "ENGR210", "ENGR140", "ENGR110", "ENGR125",
]
PREFERRED_TERMS = ["202630", "202570", "202530", "202470"]


def _load_csv(name: str) -> list[dict[str, str]]:
    with (CONFIG_DIR / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_courses_table() -> list[dict]:
    """One row per target course: key, title, units, institution_id, catalog_year."""
    rows = []
    for course_key in TARGET_COURSES:
        found = None
        for term_code in PREFERRED_TERMS:
            for subject_file in (BANNER_DIR / f"term={term_code}").glob("*.json"):
                sections = json.loads(subject_file.read_text(encoding="utf-8"))
                match = next((s for s in sections if s["subjectCourse"] == course_key), None)
                if match:
                    found = match
                    break
            if found:
                break
        if not found:
            print(f"WARNING: {course_key} not found in any preferred term for courses table")
            continue
        rows.append(
            {
                "course_key": course_key,
                "title": found["courseTitle"],
                "units": found["creditHourLow"],
                "institution_id": "avc",
                "catalog_year": "2025-26",
            }
        )
    return rows


def build_articulation_table() -> list[dict]:
    """Flatten every staged ASSIST agreement into rows."""
    majors = {row["major_key"]: row for row in _load_csv("majors.csv")}
    rows = []
    for path in sorted(ASSIST_DIR.glob("*.json")):
        # filenames are avc-to-<receiving>-<major_key>-<academic_year>.json
        stem = path.stem
        major_key = next((mk for mk in majors if f"-{mk}-" in stem), None)
        if major_key is None:
            print(f"WARNING: could not infer major_key for {path.name}, skipping")
            continue
        major = majors[major_key]
        agreement = json.loads(path.read_text(encoding="utf-8"))
        articulation_rows = flatten_agreement(
            agreement,
            major_key=major_key,
            sending_institution_id="avc",
            receiving_institution_id=major["institution_id"],
        )
        rows.extend(asdict(r) for r in articulation_rows)
    return rows


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    courses = build_courses_table()
    (OUT_DIR / "courses.json").write_text(json.dumps(courses, indent=2), encoding="utf-8")
    print(f"courses.json: {len(courses)} rows")

    articulation = build_articulation_table()
    (OUT_DIR / "articulation.json").write_text(json.dumps(articulation, indent=2), encoding="utf-8")
    not_articulated = sum(1 for r in articulation if r["status"] == "not_articulated")
    print(f"articulation.json: {len(articulation)} rows ({not_articulated} not_articulated)")

    offering_src = PROCESSED_DIR / "banner" / "offering_patterns.json"
    offering_dst = OUT_DIR / "offering_pattern.json"
    offering_dst.write_text(offering_src.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"offering_pattern.json: copied from {offering_src.relative_to(ROOT)}")

    ge_src = PROCESSED_DIR / "assist_ge" / "ge_certification.json"
    ge_dst = OUT_DIR / "ge_certification.json"
    ge_dst.write_text(ge_src.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"ge_certification.json: copied from {ge_src.relative_to(ROOT)}")

    prereq_src = PROCESSED_DIR / "banner" / "prereq_graph_reviewed.json"
    prereq_dst = OUT_DIR / "prereq_graph.json"
    prereq_dst.write_text(prereq_src.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"prereq_graph.json: copied from {prereq_src.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
