"""Run offering-pattern derivation over the Banner backfill -- Phase 1a-derived
(docs/architecture.md).

Reads data/raw/banner/, writes data/processed/banner/offering_patterns.json
(gitignored -- this is a derived artifact, not yet human-reviewed). Per the plan's
build-time HITL gate ("Offering pattern sanity check | Confirm 10 known patterns
against advisor knowledge"), this script also prints a sample for spot-checking
rather than silently trusting its own output.

Usage:
    python3 scripts/derive_offering_patterns.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transfer_advisor.pipelines import derive_offering_patterns, load_backfill  # noqa: E402
from transfer_advisor.pipelines.offering_patterns import to_json  # noqa: E402

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "banner"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "banner" / "offering_patterns.json"


def main() -> int:
    backfill = load_backfill(RAW_DIR)
    if not backfill:
        print(f"No backfill data found under {RAW_DIR} -- run scripts/fetch_banner_backfill.py first.")
        return 1

    patterns = derive_offering_patterns(backfill)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(to_json(patterns), encoding="utf-8")
    print(f"Wrote {len(patterns)} course offering patterns to {OUT_PATH}")

    label_counts: dict[str, int] = {}
    for p in patterns:
        label_counts[p.pattern_label] = label_counts.get(p.pattern_label, 0) + 1
    print("\nLabel distribution:")
    for label, count in sorted(label_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {label:<18} {count}")

    print("\nSample for human spot-check (per docs/architecture.md's HITL gate):")
    sample = [p for p in patterns if p.pattern_label not in ("insufficient_data",)][:10]
    for p in sample:
        print(
            f"  {p.course_key:<10} {p.pattern_label:<18} "
            f"fall={p.fall_count} spring={p.spring_count} summer={p.summer_count} winter={p.winter_count} "
            f"(of {p.terms_observed} terms, {p.years_covered} years) last={p.last_offered_term}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
