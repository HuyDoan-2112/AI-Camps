"""Join ASSIST-referenced AVC courses against the Banner backfill -- Phase 2
(docs/architecture.md).

For every AVC (sending-side) course_key referenced in the staged ASSIST agreements
(data/raw/assist/), check whether it was actually observed in the Banner backfill
(data/raw/banner/). Prints match/unmatched counts and -- critically -- the full
unmatched list, since the plan is explicit: "Log every unmatched pair to a report
-- never silently drop. An unmatched requirement is a student getting bad advice."

An unmatched course isn't necessarily wrong: it may be offered under a subject we
didn't backfill, may have been renumbered, or may genuinely no longer be offered.
This script reports the mismatch for human review and never silently rewrites it.

Usage:
    python3 scripts/join_assist_banner.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transfer_advisor.pipelines import normalize_course_key  # noqa: E402

ASSIST_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "assist"
BANNER_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "banner"


def _assist_referenced_avc_courses() -> dict[str, list[str]]:
    """Returns {normalized_course_key: [agreement files that reference it]}."""
    referenced: dict[str, list[str]] = {}
    for path in sorted(ASSIST_DIR.glob("*.json")):
        agreement = json.loads(path.read_text(encoding="utf-8"))
        for entry in agreement.get("articulations", []):
            sending = entry.get("articulation", {}).get("sendingArticulation", {})
            for group in sending.get("items", []):
                for course in group.get("items", []):
                    key = normalize_course_key(f"{course['prefix']}{course['courseNumber']}")
                    referenced.setdefault(key, []).append(path.name)
    return referenced


def _banner_observed_courses() -> set[str]:
    observed: set[str] = set()
    for term_dir in BANNER_DIR.glob("term=*"):
        for subject_file in term_dir.glob("*.json"):
            rows = json.loads(subject_file.read_text(encoding="utf-8"))
            for row in rows:
                observed.add(normalize_course_key(row["subjectCourse"]))
    return observed


def main() -> int:
    referenced = _assist_referenced_avc_courses()
    observed = _banner_observed_courses()

    matched = sorted(k for k in referenced if k in observed)
    unmatched = sorted(k for k in referenced if k not in observed)

    total = len(referenced)
    match_rate = len(matched) / total * 100 if total else 0.0

    print(f"ASSIST-referenced AVC courses: {total}")
    print(f"Matched in Banner backfill:    {len(matched)} ({match_rate:.0f}%)")
    print(f"Unmatched:                     {len(unmatched)}")
    print()

    if unmatched:
        print("Unmatched courses (never silently dropped -- review each):")
        for key in unmatched:
            agreements = ", ".join(sorted(set(referenced[key])))
            print(f"  {key:<12} referenced by: {agreements}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
