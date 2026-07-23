"""Repository-root default and hosted-layout override tests."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from transfer_advisor._project_root import project_root


class ProjectRootTest(unittest.TestCase):
    def test_env_var_overrides_default(self) -> None:
        with patch.dict(os.environ, {"TRANSFER_ADVISOR_ROOT": "/app"}):
            self.assertEqual(project_root(), Path("/app"))

    def test_default_resolves_to_real_repo_root(self) -> None:
        # Without the env var, confirm the walk-up actually lands on a
        # directory that has config/ and data/ as children -- not just that
        # it returns *some* path.
        os.environ.pop("TRANSFER_ADVISOR_ROOT", None)
        root = project_root()
        self.assertTrue((root / "config").is_dir())
        self.assertTrue((root / "data").is_dir())


if __name__ == "__main__":
    unittest.main()
