from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


_app: QApplication | None = None


def setUpModule():
    global _app
    if QApplication.instance() is None:
        _app = QApplication(sys.argv)
    else:
        _app = QApplication.instance()


def tearDownModule():
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


class TestUISmoke(unittest.TestCase):
    def test_main_window_constructs(self) -> None:
        win = MainWindow()
        self.assertIsNotNone(win.stackedWidget)

    def test_settings_and_project_tree_construct(self) -> None:
        from ui.pages.settings_page import SettingsPage
        from ui.widgets.project_tree import ProjectTreeWidget

        self.assertIsNotNone(SettingsPage())
        self.assertIsNotNone(ProjectTreeWidget())

    def test_support_pages_construct(self) -> None:
        from ui.pages.analysis_page import AnalysisPage
        from ui.pages.chart_page import ChartPage
        from ui.pages.data_page import DataPage
        from ui.pages.digitize_page import DigitizePage

        self.assertIsNotNone(DataPage())
        self.assertIsNotNone(ChartPage())
        self.assertIsNotNone(AnalysisPage())
        self.assertIsNotNone(DigitizePage())
