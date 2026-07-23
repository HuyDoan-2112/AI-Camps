"""AVC Banner section fetcher -- Phase 1a (docs/architecture.md).

Writes RAW section rows per (subject, term) to
data/raw/banner/term=<term_code>/<subject>.json -- mirrors the eventual S3 raw
zone layout. data/raw/ is gitignored on purpose.

This hits AVC's live production registration system -- be polite. Defaults to a
small sample (one recent term, one subject) so a plain run doesn't accidentally
kick off the full 12-15-term historical backfill. Pass --terms/--subjects
explicitly to run a larger, deliberate backfill.

Usage:
    python3 scripts/fetch_banner_backfill.py
    python3 scripts/fetch_banner_backfill.py --terms 202630,202570,202510 \\
        --subjects MATH,PHYS,CHEM,ENGR,CS,ENGL
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transfer_advisor.pipelines import BannerSession, search_sections  # noqa: E402

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "banner"

DEFAULT_TERMS = ["202630"]  # Spring 2026 -- a small, recent sample
DEFAULT_SUBJECTS = ["MATH"]
# Delay between (subject, term) requests -- distinct from search_sections()'s
# own inter-page delay. Running this serially from one client is already
# gentler than the eventual Step Functions fan-out, but a full backfill is
# still ~90 sequential requests against a live production system; space them out.
INTER_REQUEST_DELAY_SECONDS = 0.4


def main(terms: list[str], subjects: list[str]) -> int:
    session = BannerSession()

    for term_code in terms:
        session.register_term(term_code)
        term_dir = RAW_DIR / f"term={term_code}"
        term_dir.mkdir(parents=True, exist_ok=True)

        for subject in subjects:
            rows = search_sections(session, subject, term_code)
            out_path = term_dir / f"{subject}.json"
            out_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
            print(f"term={term_code} subject={subject}: wrote {out_path} ({len(rows)} sections)")
            time.sleep(INTER_REQUEST_DELAY_SECONDS)

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terms", type=lambda s: s.split(","), default=DEFAULT_TERMS)
    parser.add_argument("--subjects", type=lambda s: s.split(","), default=DEFAULT_SUBJECTS)
    args = parser.parse_args()
    raise SystemExit(main(args.terms, args.subjects))
