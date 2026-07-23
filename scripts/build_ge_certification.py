"""Fetch and flatten AVC's real Cal-GETC certification list -- v2
(docs/architecture.md's "GE is cheaper than it looks" note).

Live ASSIST fetch + flatten in one script, matching build_kb_content.py's
convention for a single small transform (not a multi-term backfill like
Banner's fetch/derive split). Reads data/raw/assist_ge/avc_calgetc_2025-26.json
if it already exists (skip a redundant live fetch); otherwise fetches fresh.

Usage:
    python3 scripts/build_ge_certification.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transfer_advisor.pipelines.assist_seed import AssistSession, get_ge_certification_courses  # noqa: E402
from transfer_advisor.pipelines.ge_certification import flatten_ge_certification  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW_PATH = ROOT / "data" / "raw" / "assist_ge" / "avc_calgetc_2025-26.json"
OUT_PATH = ROOT / "data" / "processed" / "assist_ge" / "ge_certification.json"

AVC_INSTITUTION_ID = 121
ACADEMIC_YEAR_ID = 76  # fallYear=2025 -> "2025-26", matching this project's convention throughout


def main() -> int:
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    if RAW_PATH.exists():
        raw = json.loads(RAW_PATH.read_text(encoding="utf-8"))
        print(f"Reusing cached raw response at {RAW_PATH}")
    else:
        session = AssistSession()
        raw = get_ge_certification_courses(session, AVC_INSTITUTION_ID, ACADEMIC_YEAR_ID, list_type="CalGETC")
        RAW_PATH.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        print(f"Fetched and wrote raw response to {RAW_PATH}")

    print(f"{len(raw.get('courseInformationList', []))} raw rows (includes historical/inactive)")

    courses = flatten_ge_certification(raw)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps([asdict(c) for c in courses], indent=2), encoding="utf-8")
    print(f"Wrote {len(courses)} currently-active Cal-GETC courses to {OUT_PATH}")

    area_counts: dict[str, int] = {}
    for c in courses:
        for a in c.areas:
            area_counts[a.code] = area_counts.get(a.code, 0) + 1
    print("\nCourses per Cal-GETC area:")
    for code, count in sorted(area_counts.items()):
        print(f"  {code:<6} {count}")

    print("\nSample for human spot-check:")
    for c in courses[:10]:
        area_codes = ", ".join(a.code for a in c.areas)
        print(f"  {c.course_key:<12} {c.title:<45} areas=[{area_codes}]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
