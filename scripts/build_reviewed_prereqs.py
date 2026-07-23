"""Encode the human-reviewed ME-pathway prerequisite graph -- Phase 2
(docs/architecture.md).

Not a parser -- this encodes the specific resolutions a human confirmed for
each of the 12 courses' extracted clauses, including the 8 that required manual
review. The draft can be regenerated with `scripts/extract_prereqs.py`.

Review provenance: Claude proposed a read for each flagged clause (raw text +
reasoning); the project owner confirmed all of them in conversation, then
independently verified all 12 courses row-by-row against AVC's live Banner
catalog directly (2026-07-22). This satisfies the plan's build-time HITL gate
for this course set.

Usage:
    python3 scripts/build_reviewed_prereqs.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "banner" / "prereq_graph_reviewed.json"


@dataclass(frozen=True)
class ReviewedPrerequisites:
    course_key: str
    requires_all_of: tuple[str, ...] = ()
    requires_one_of: tuple[str, ...] = ()
    corequisite_of: tuple[str, ...] = ()
    advisory_only: tuple[str, ...] = ()
    notes: str = ""


REVIEWED: list[ReviewedPrerequisites] = [
    ReviewedPrerequisites(
        course_key="MATH150",
        requires_one_of=("MATH140", "MATH149"),
        notes="Or placement by multiple measures (non-course alternative, not encoded as a course edge).",
    ),
    ReviewedPrerequisites(
        course_key="MATH160",
        requires_one_of=("MATH150", "MATH150H"),
        notes="Or placement by multiple measures.",
    ),
    ReviewedPrerequisites(
        course_key="MATH250",
        requires_all_of=("MATH160",),
    ),
    ReviewedPrerequisites(
        course_key="MATH230",
        requires_all_of=("MATH160",),
        advisory_only=("MATH220", "MATH250"),
    ),
    ReviewedPrerequisites(
        course_key="MATH220",
        requires_all_of=("MATH160",),
    ),
    ReviewedPrerequisites(
        course_key="PHYS110",
        corequisite_of=("MATH150",),
        advisory_only=("PSCI101", "ENGL101"),
    ),
    ReviewedPrerequisites(
        course_key="PHYS120",
        requires_all_of=("PHYS110",),
        corequisite_of=("MATH160",),
        advisory_only=("ENGL101",),
        notes=(
            "Raw text sat under one 'Corequisite:' label but was two sentences: "
            "'Completion of PHYS 110.' (no concurrent-enrollment language -> "
            "treated as a hard prerequisite) and 'Completion of or concurrent "
            "enrollment in MATH 160.' (-> corequisite). Split on human review."
        ),
    ),
    ReviewedPrerequisites(
        course_key="CHEM110",
        advisory_only=("CHEM101",),
        notes=(
            "Raw prerequisite text says 'Completion of Intermediate Algebra or "
            "higher or placement by multiple measures.' No AVC course titled or "
            "coded as Intermediate Algebra was found in the Banner backfill "
            "(checked MATH.json across all terms). Likely legacy catalog text "
            "predating AB 705's elimination of standalone remedial math "
            "courses. Treated as no hard course-level math prerequisite -- "
            "flag for a human to double check against AVC's current catalog "
            "if this matters for a specific student."
        ),
    ),
    ReviewedPrerequisites(
        course_key="ENGR210",
        requires_all_of=("MATH160", "PHYS110"),
    ),
    ReviewedPrerequisites(
        course_key="ENGR140",
        requires_one_of=("MATH135",),
        notes=(
            "Raw text says 'MATH 135 or higher or placement by multiple "
            "measures.' Only MATH135 itself is encoded; any higher-numbered "
            "MATH course should also satisfy this in practice but isn't "
            "structurally captured. Low stakes -- ENGR140 doesn't gate any "
            "other course in this graph."
        ),
    ),
    ReviewedPrerequisites(
        course_key="ENGR110",
        notes="No Prerequisite/Corequisite/Advisory clause found in the catalog text.",
    ),
    ReviewedPrerequisites(
        course_key="ENGR125",
        requires_all_of=("MATH150",),
    ),
]


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "reviewed": True,
        "review_provenance": (
            "Claude proposed a read for each flagged clause; the project owner "
            "confirmed all of them in conversation, then independently verified "
            "all 12 courses row-by-row against AVC's live Banner catalog "
            "directly (2026-07-22)."
        ),
        "courses": [asdict(r) for r in REVIEWED],
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(REVIEWED)} reviewed prerequisite records to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
