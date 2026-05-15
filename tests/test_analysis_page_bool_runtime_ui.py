from __future__ import annotations

import unittest

import os
import sys
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core.extension_loader import reload_builtin_extensions
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
        reload_builtin_extensions()
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

    def test_builtin_extension_run_uses_selected_inputs_when_lines_list_is_empty(self) -> None:
        from models.schemas import DataFile, DataSeries

        other = DataFile(name="other.csv", series=[DataSeries(name="other", x=[0.0, 1.0, 2.0], y=[1.0, 1.5, 2.0])])
        self.pm.add_data_file(other)

        self.page._refresh_analysis_type_choices()
        self.page.on_tree_node_activated("series", self.series.id)
        other_series = self.pm.current_project.data_files[-1].series[0]
        self.page.on_tree_node_activated("series", other_series.id)
        self.page._type_combo.setCurrentIndex(self.page._analysis_type_ids.index("interface_contract_analysis"))
        self.page._extension_params_edit.set_options({"lines_list": []})
        self.page._on_extension_analysis_options_changed({"lines_list": []})

        def _sync_run(_category, job_id, func, args=(), on_finished=None, on_error=None, **_kwargs):
            self.page._task_manager._current_job_ids["analysis"] = job_id
            try:
                value = func(*args)
            except Exception as exc:  # pragma: no cover - surfaced by assertions below
                if on_error is not None:
                    on_error("analysis", f"{type(exc).__name__}: {exc}")
                raise
            if on_finished is not None:
                on_finished("analysis", value)

        with mock.patch.object(self.page._task_manager, "run", side_effect=_sync_run), \
             mock.patch.object(self.page._task_manager, "get_task", return_value=None):
            self.page._run_analysis()

        self.assertIsInstance(self.page._result, dict)
        self.assertEqual(self.page._result.get("analysis_type"), "interface_contract_analysis")
        summary_items = self.page._result.get("summary_items") or []
        self.assertTrue(summary_items)


if __name__ == "__main__":
    unittest.main()
