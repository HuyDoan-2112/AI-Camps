"""First deterministic unit test: the seeded config/*.csv files satisfy their contract."""

import unittest

from scripts.validate_config import main


class ConfigContractsTest(unittest.TestCase):
    def test_seeded_config_passes_validation(self) -> None:
        self.assertEqual(main(), 0)


if __name__ == "__main__":
    unittest.main()
