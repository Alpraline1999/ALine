from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core import ui_preferences
from core.i18n import reload_translations
from ui.pages.process_page import ProcessPage
from ui.pages.settings_page import SettingsPage


_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    if QApplication.instance() is None:
        _app = QApplication(sys.argv)
    else:
        _app = QApplication.instance()


def tearDownModule() -> None:
    global _app
    app = QApplication.instance()
    if app is not None:
        for widget in list(app.topLevelWidgets()):
            try:
                widget.close()
                widget.deleteLater()
            except RuntimeError:
                continue
        app.processEvents()
    _app = None


class TestSettingsPageRefresh(unittest.TestCase):
    def test_refresh_templates_without_legacy_template_widgets_does_not_crash(self) -> None:
        page = SettingsPage()
        page._tmpl_card = None
        page._tmpl_list = None
        page.refresh_templates()

    def test_refresh_templates_without_template_list_attribute_does_not_crash(self) -> None:
        page = SettingsPage()
        page._tmpl_card = None
        if hasattr(page, "_tmpl_list"):
            delattr(page, "_tmpl_list")
        page.refresh_templates()

    def test_process_page_refresh_input_choices_exists_for_runtime_language_refresh(self) -> None:
        page = ProcessPage()
        page.refresh_input_choices()

    def test_refresh_language_ui_rebuilds_translated_language_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            original_config_path = ui_preferences._CONFIG_PATH
            ui_preferences._CONFIG_PATH = Path(tmp) / "ui_preferences.json"
            try:
                ui_preferences.set_ui_language("en_US")
                reload_translations()

                page = SettingsPage()
                try:
                    page.refresh_language_ui()
                    QApplication.processEvents()
                    self.assertIsNotNone(page._lang_card)
                    self.assertEqual(page._lang_card.titleLabel.text(), "Language")
                    self.assertEqual(
                        page._lang_card.contentLabel.text(),
                        "Switch the application language. Restart to apply fully.",
                    )
                finally:
                    page.deleteLater()
                    QApplication.processEvents()
            finally:
                ui_preferences.set_ui_language("zh_CN")
                reload_translations()
                ui_preferences._CONFIG_PATH = original_config_path

    def test_refresh_language_ui_translates_external_extension_add_folder_button(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            original_config_path = ui_preferences._CONFIG_PATH
            ui_preferences._CONFIG_PATH = Path(tmp) / "ui_preferences.json"
            try:
                ui_preferences.set_ui_language("en_US")
                reload_translations()

                page = SettingsPage()
                try:
                    self.assertEqual(page._external_extensions_dirs_card.addFolderButton.text(), "Add Folder")
                    page.refresh_language_ui()
                    QApplication.processEvents()
                    self.assertEqual(page._external_extensions_dirs_card.addFolderButton.text(), "Add Folder")
                finally:
                    page.deleteLater()
                    QApplication.processEvents()
            finally:
                ui_preferences.set_ui_language("zh_CN")
                reload_translations()
                ui_preferences._CONFIG_PATH = original_config_path
