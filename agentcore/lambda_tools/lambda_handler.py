"""Gateway Lambda adapter for live Banner facts and deterministic validation."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

DEPLOYMENT_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = (
    DEPLOYMENT_ROOT
    if (DEPLOYMENT_ROOT / "src").is_dir()
    else DEPLOYMENT_ROOT.parents[1]
)
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("TRANSFER_ADVISOR_ROOT", str(PROJECT_ROOT))

import requests  # noqa: E402

from transfer_advisor.planning.validate_plan import validate_proposed_plan  # noqa: E402
from transfer_advisor.tools.live_sections import get_live_course_sections  # noqa: E402


def _gateway_tool_name(context: Any) -> str:
    client_context = getattr(context, "client_context", None)
    custom = getattr(client_context, "custom", None) or {}
    qualified_name = str(custom.get("bedrockAgentCoreToolName") or "")
    if "___" not in qualified_name:
        raise ValueError("Gateway tool name is missing from the Lambda context.")
    return qualified_name.rsplit("___", 1)[-1]


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Dispatch the Gateway tool call without adding agent or planning logic."""
    tool_name = _gateway_tool_name(context)
    if tool_name == "get_live_course_sections":
        try:
            return get_live_course_sections(
                course=str(event.get("course") or ""),
                term=str(event.get("term") or ""),
            )
        except (ValueError, requests.RequestException) as error:
            return {
                "ok": False,
                "error": str(error),
                "warning": (
                    "Live Banner data is temporarily unavailable or the course/term "
                    "was not recognized. Confirm availability in AVC Banner."
                ),
            }
    if tool_name == "validate_transfer_plan":
        return validate_proposed_plan(
            major=str(event.get("major") or ""),
            completed_courses=list(event.get("completed_courses") or []),
            terms=list(event.get("terms") or []),
            min_units_per_term=event.get("min_units_per_term"),
            max_units_per_term=event.get("max_units_per_term"),
            max_stem_per_term=event.get("max_stem_per_term"),
        )
    raise ValueError(f"Unsupported Gateway tool: {tool_name}")
