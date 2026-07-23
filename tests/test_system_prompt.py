"""Behavior contracts for the managed advising prompt."""

from __future__ import annotations

import unittest

from transfer_advisor._project_root import project_root


class SystemPromptTest(unittest.TestCase):
    def test_prompt_is_compact_and_does_not_assume_a_pathway(self) -> None:
        prompt = (
            project_root() / "agentcore" / "system_prompt.md"
        ).read_text(encoding="utf-8")

        self.assertIn("Do not assume or introduce a destination", prompt)
        self.assertIn("Use prior conversation details only when relevant", prompt)
        self.assertIn("ask a short clarifying question", prompt)
        self.assertIn("summer and winter at 6 units or fewer", prompt)
        self.assertLess(len(prompt.split()), 400)


if __name__ == "__main__":
    unittest.main()
