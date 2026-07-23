"""Resolve the repository root for versioned config and runtime data.

Streamlit normally runs from the repository checkout, where the default parent
walk is correct. ``TRANSFER_ADVISOR_ROOT`` supports container or hosted layouts
that place the package and data in different directories.
"""

from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    env_root = os.environ.get("TRANSFER_ADVISOR_ROOT")
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parents[2]
