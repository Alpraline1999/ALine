from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tests.ui_test_helpers import patch_global_assets, patch_pm, make_project


_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication(sys.argv)


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


class TestMainWindowRuntimePaths(unittest.TestCase):
    def setUp(self) -> None:
        self._restore_assets = patch_global_assets()
        self.pm, self.project, self.df, self.series = make_project("main_window_runtime")
        self._restore_pm = patch_pm(self.pm)

        import app.project_tree_command_service as project_tree_command_service

        self._original_command_service_pm = project_tree_command_service.project_manager
        project_tree_command_service.project_manager = self.pm

        from ui.main_window import MainWindow

        self.win = MainWindow()
        QApplication.processEvents()

    def tearDown(self) -> None:
        import app.project_tree_command_service as project_tree_command_service

        self.win.close()
        self.win.deleteLater()
        project_tree_command_service.project_manager = self._original_command_service_pm
        self._restore_pm()
        self._restore_assets()
        QApplication.processEvents()

    def test_save_current_project_from_panel_does_not_shadow_translation_function(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = str(Path(tmp) / "runtime.aline")
            self.pm.current_project.file_path = project_path

            with mock.patch("ui.main_window.show_success") as success_mock:
                saved = self.win._save_current_project_from_panel()

            self.assertTrue(saved)
            success_mock.assert_called_once()

    def test_save_current_project_as_from_panel_does_not_shadow_translation_function(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = str(Path(tmp) / "runtime-save-as.aline")

            with mock.patch("ui.main_window.QFileDialog.getSaveFileName", return_value=(project_path, "ALine 项目")), \
                 mock.patch("ui.main_window.show_success") as success_mock:
                saved = self.win._save_current_project_as_from_panel()

            self.assertTrue(saved)
            success_mock.assert_called_once()

if __name__ == "__main__":
    unittest.main()
