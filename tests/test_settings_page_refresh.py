from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

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
