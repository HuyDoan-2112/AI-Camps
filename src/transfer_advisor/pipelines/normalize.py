"""Course-key normalization -- Phase 2 (docs/architecture.md).

"MATH 150" / "MATH150" / "Math 150 " -> "MATH150". Uppercase, strip whitespace and
punctuation. This is the single function every source (ASSIST, Banner, catalog)
must funnel course identifiers through before joining across sources -- a
mismatched course_key here is exactly how a real course silently gets treated as
not-offered or not-articulated.
"""

from __future__ import annotations

import re

_NON_WORD = re.compile(r"[^\w]")


def normalize_course_key(raw: str) -> str:
    return _NON_WORD.sub("", raw).upper()
