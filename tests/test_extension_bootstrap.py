from __future__ import annotations

import unittest

from core.extension_bootstrap import ensure_builtin_extensions_loaded
from core.extension_api import extension_registry


class TestExtensionBootstrap(unittest.TestCase):
    def test_builtin_extensions_load_idempotently(self) -> None:
        ensure_builtin_extensions_loaded(extension_registry)
        first_processing = {item.type for item in extension_registry.list_processing()}

        ensure_builtin_extensions_loaded(extension_registry)
        second_processing = {item.type for item in extension_registry.list_processing()}

        self.assertEqual(first_processing, second_processing)
        self.assertIn("crop", first_processing)


if __name__ == "__main__":
    unittest.main()
