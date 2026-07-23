"""Student-facing Streamlit shell contracts."""

from __future__ import annotations

import unittest

from streamlit.testing.v1 import AppTest

from transfer_advisor._project_root import project_root


class StreamlitUiTest(unittest.TestCase):
    def test_welcome_screen_is_clean_and_actionable(self) -> None:
        app = AppTest.from_file(project_root() / "streamlit_app.py").run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(len(app.expander), 0)
        self.assertEqual(len(app.button), 4)
        self.assertEqual(len(app.chat_input), 1)


if __name__ == "__main__":
    unittest.main()
