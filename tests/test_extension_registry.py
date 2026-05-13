from __future__ import annotations

import unittest

from core.extension_definition import (
    AnalysisExtension,
    DigitizeExtension,
    PlotExtension,
    ProcessingExtension,
)
from core.extension_registry import ExtensionRegistry


class TestExtensionRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = ExtensionRegistry()

    # -- register + get ------------------------------------------------

    def test_register_and_get_processing(self):
        ext = ProcessingExtension(
            type="test",
            name="测试",
            handler=lambda l, p: l[0],
            source_kind="builtin",
        )
        self.registry.register_processing(ext)
        self.assertEqual(self.registry.get_processing("test"), ext)

    def test_register_and_get_analysis(self):
        ext = AnalysisExtension(
            type="test_analysis",
            name="分析测试",
            handler=lambda l, p: {"result": 42},
            source_kind="builtin",
        )
        self.registry.register_analysis(ext)
        self.assertEqual(self.registry.get_analysis("test_analysis"), ext)

    # -- conflict resolution -------------------------------------------

    def test_register_duplicate_type_overwrites(self):
        """Duplicate type raises ValueError across any source kind."""
        ext1 = ProcessingExtension(
            type="same",
            name="旧",
            handler=lambda l, p: l[0],
            source_kind="builtin",
        )
        ext2 = ProcessingExtension(
            type="same",
            name="新",
            handler=lambda l, p: l[0],
            source_kind="builtin",
        )
        self.registry.register_processing(ext1)
        with self.assertRaisesRegex(ValueError, "重复的 processing 扩展 type: same"):
            self.registry.register_processing(ext2)
        self.assertEqual(self.registry.get_processing("same").name, "旧")

    def test_builtin_does_not_overwrite_external(self):
        """Different source_kind → ValueError raised on conflict."""
        ext_ext = ProcessingExtension(
            type="x",
            name="外部",
            handler=lambda l, p: l[0],
            source_kind="external",
        )
        ext_builtin = ProcessingExtension(
            type="x",
            name="内置",
            handler=lambda l, p: l[0],
            source_kind="builtin",
        )
        self.registry.register_processing(ext_ext)
        with self.assertRaisesRegex(ValueError, "重复的 processing 扩展 type: x"):
            self.registry.register_processing(ext_builtin)
        self.assertEqual(self.registry.get_processing("x").name, "外部")

    # -- edge cases ----------------------------------------------------

    def test_get_nonexistent_returns_none(self):
        self.assertIsNone(self.registry.get_processing("nonexistent"))
        self.assertIsNone(self.registry.get_analysis("nonexistent"))
        self.assertIsNone(self.registry.get_plot("nonexistent"))
        self.assertIsNone(self.registry.get_digitize("nonexistent"))

    # -- introspection helpers -----------------------------------------

    def test_get_categories_returns_all_types(self):
        cats = self.registry.get_categories()
        self.assertIn("processing", cats)
        self.assertIn("analysis", cats)
        self.assertIn("plot", cats)
        self.assertIn("digitize", cats)
        self.assertIsInstance(cats["processing"], list)
        self.assertIsInstance(cats["analysis"], list)
        self.assertIsInstance(cats["plot"], list)
        self.assertIsInstance(cats["digitize"], list)

    def test_detect_conflicts_no_conflicts(self):
        self.assertEqual(self.registry.detect_conflicts(), [])
