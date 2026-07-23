"""One-time fetch of ASSIST articulation agreements, per docs/architecture.md Phase 1b.

Writes the RAW response for each requested major to
data/raw/assist/avc-to-<receiving>-<major_key>-<academic_year>.json for human review.
This is NOT a reviewed seed file -- per the build-time HITL gate in
docs/architecture.md, a human must verify at least one full agreement row-by-row
against assist.org before anything derived from this is trusted. data/raw/ is
gitignored on purpose; promote a file to data/fixtures/ only after that review.

Usage:
    python3 scripts/fetch_assist_seed.py me_ucla
    python3 scripts/fetch_assist_seed.py ee_ucla me_cpp ee_cpp
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transfer_advisor.pipelines import AssistSession, get_articulation_agreement  # noqa: E402

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "assist"

# ASSIST academic-year IDs aren't the same as the "YYYY-YY" strings in majors.csv.
# This mapping was observed live via get_academic_years() on 2026-07-21 -- id 77
# (fallYear 2026) exists but had zero published reports at that time; id 76 was the
# latest fully published year. Re-derive if this drifts.
_ACADEMIC_YEAR_TO_ASSIST_ID = {"2025-26": 76}


def _load_csv(name: str) -> list[dict[str, str]]:
    with (CONFIG_DIR / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main(major_keys: list[str]) -> int:
    institutions = {row["institution_id"]: row for row in _load_csv("institutions.csv")}
    majors = {row["major_key"]: row for row in _load_csv("majors.csv")}
    sending = institutions["avc"]

    session = AssistSession()
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    for major_key in major_keys:
        major = majors[major_key]
        receiving = institutions[major["institution_id"]]
        academic_year_id = _ACADEMIC_YEAR_TO_ASSIST_ID[major["academic_year"]]
        key = (
            f"{academic_year_id}/{sending['assist_id']}/to/{receiving['assist_id']}"
            f"/Major/{major['assist_major_guid']}"
        )

        agreement = get_articulation_agreement(session, key)

        out_path = RAW_DIR / f"avc-to-{major['institution_id']}-{major_key}-{major['academic_year']}.json"
        out_path.write_text(json.dumps(agreement, indent=2), encoding="utf-8")
        print(f"{major_key}: wrote {out_path} ({len(agreement['articulations'])} articulation rows)")

    return 0


if __name__ == "__main__":
    requested = sys.argv[1:] or ["me_ucla"]
    raise SystemExit(main(requested))
