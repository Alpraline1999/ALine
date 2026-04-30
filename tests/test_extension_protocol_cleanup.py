from __future__ import annotations

import unittest

from core.extension_api import normalize_extension_lines_list


class TestExtensionProtocolCleanup(unittest.TestCase):
    def test_lines_list_sentinals_are_rejected(self) -> None:
        for raw in ("all", ":", "*", "selected"):
            with self.assertRaises(ValueError):
                normalize_extension_lines_list(raw)


if __name__ == "__main__":
    unittest.main()
