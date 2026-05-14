from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path

from core import ui_preferences
from core.i18n import _, gettext_translate


class TestI18n(unittest.TestCase):
    def test_gettext_fallback_returns_source_text(self) -> None:
        self.assertEqual(_("中文"), "中文")
        self.assertEqual(gettext_translate("分析扩展"), "分析扩展")

    def test_ui_language_preference_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            original = ui_preferences._CONFIG_PATH
            ui_preferences._CONFIG_PATH = Path(tmp) / "ui_preferences.json"
            try:
                self.assertEqual(ui_preferences.set_ui_language("en_US"), "en_US")
                self.assertEqual(ui_preferences.get_ui_language(), "en_US")
                self.assertEqual(ui_preferences.set_ui_language("unknown"), "zh_CN")
                self.assertEqual(ui_preferences.get_ui_language(), "zh_CN")
            finally:
                ui_preferences._CONFIG_PATH = original

    def test_i18n_reload_respects_language_preference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            original = ui_preferences._CONFIG_PATH
            ui_preferences._CONFIG_PATH = Path(tmp) / "ui_preferences.json"
            try:
                ui_preferences.set_ui_language("en_US")
                i18n = importlib.reload(importlib.import_module("core.i18n"))
                self.assertEqual(i18n._("主页"), "Home")
                self.assertEqual(gettext_translate("数据管理"), "Data Management")
            finally:
                ui_preferences._CONFIG_PATH = original
