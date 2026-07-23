"""Gateway Lambda dispatch remains a thin adapter around domain tools."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agentcore.lambda_tools.lambda_handler import handler
from infra.build_advisor_tools_lambda import build_advisor_tools_package


def _context(tool_name: str):
    return SimpleNamespace(
        client_context=SimpleNamespace(
            custom={
                "bedrockAgentCoreToolName": f"advisor-tools___{tool_name}",
            }
        )
    )


class AdvisorToolsLambdaTest(unittest.TestCase):
    def test_dispatches_live_lookup(self) -> None:
        expected = {"ok": True, "sections": []}
        with patch(
            "agentcore.lambda_tools.lambda_handler.get_live_course_sections",
            return_value=expected,
        ) as lookup:
            result = handler(
                {"course": "MATH150", "term": "Fall 2026"},
                _context("get_live_course_sections"),
            )

        self.assertEqual(result, expected)
        lookup.assert_called_once_with(course="MATH150", term="Fall 2026")

    def test_dispatches_validator_without_creating_a_plan(self) -> None:
        result = handler(
            {
                "major": "me_ucla",
                "completed_courses": [],
                "terms": [],
            },
            _context("validate_transfer_plan"),
        )

        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["code"], "empty_plan")

    def test_package_contains_handler_code_and_reviewed_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "tools.zip"
            build_advisor_tools_package(output, install_dependencies=False)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())

        self.assertIn("lambda_handler.py", names)
        self.assertIn(
            "src/transfer_advisor/tools/live_sections.py",
            names,
        )
        self.assertIn(
            "src/transfer_advisor/planning/validate_plan.py",
            names,
        )
        self.assertIn(
            "data/processed/structured_store/articulation.json",
            names,
        )


if __name__ == "__main__":
    unittest.main()
