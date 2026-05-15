from __future__ import annotations

import unittest

import os
import sys

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


class TestAnalysisPageBoolRuntimeUI(unittest.TestCase):
    def setUp(self) -> None:
        self._restore_assets = patch_global_assets()
        self.pm, self.project, self.df, self.series = make_project("analysis_bool_ui")
        self._restore_pm = patch_pm(self.pm)
        from ui.pages.analysis_page import AnalysisPage

        self.page = AnalysisPage()

    def tearDown(self) -> None:
        self.page.deleteLater()
        self._restore_pm()
        self._restore_assets()

    def test_run_analysis_finished_path_accepts_bool_payload(self) -> None:
        self.page.on_tree_node_activated("series", self.series.id)
        self.page._task_manager._current_job_ids["analysis"] = ""
        self.page._on_analysis_finished(
            "analysis",
            {
                "analysis_type": "bool_payload",
                "lines": True,
                "_plot_series": True,
                "summary_items": True,
                "tables": True,
                "texts": True,
            },
            "bool_payload",
            [(list(self.series.x), list(self.series.y), self.series.name)],
            "",
        )

        self.assertIsInstance(self.page._result, dict)
        self.assertEqual(self.page._result.get("lines"), [])
        self.assertEqual(self.page._result.get("_plot_series"), [])
        active_view = self.page._active_analysis_view()
        self.assertIsNotNone(active_view)
        self.assertEqual(active_view["result"].get("summary_items"), [])


if __name__ == "__main__":
    unittest.main()
