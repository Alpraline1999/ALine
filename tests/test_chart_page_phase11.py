from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.pages.chart_page import ChartPage


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


class TestChartPagePhase11(unittest.TestCase):
    def setUp(self) -> None:
        self.page = ChartPage()
        if self.page._figure is None or self.page._canvas is None:
            self.skipTest("matplotlib preview is unavailable in this environment")

    def tearDown(self) -> None:
        try:
            self.page.close()
            self.page.deleteLater()
        except RuntimeError:
            pass
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

    def test_hidden_theme_update_marks_pending_theme_redraw(self) -> None:
        self.page._view_state.pending_redraw_reason = ""
        with mock.patch.object(self.page, "_redraw") as redraw:
            self.page.update_theme()
        self.assertTrue(self.page._theme_refresh_pending)
        self.assertEqual("theme", self.page.render_diagnostics()["pending_reason"])
        redraw.assert_not_called()

    def test_visible_theme_update_uses_theme_redraw_reason(self) -> None:
        self.page.show()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        with mock.patch.object(self.page, "_schedule_redraw") as schedule:
            self.page.update_theme()
        schedule.assert_called_once_with(reason="theme")

    def test_large_curve_schedule_uses_preview_and_keeps_theme_reason(self) -> None:
        curve_a = {"name": "a", "x": list(range(6001)), "y": list(range(6001)), "visible": True}
        curve_b = {"name": "b", "x": list(range(6001)), "y": list(range(6001)), "visible": True}
        self.page._chart_series = [curve_a, curve_b]
        self.page._view_state.pending_redraw_reason = ""

        with mock.patch.object(self.page, "_decimated_redraw") as preview, mock.patch.object(self.page._redraw_timer, "start") as start:
            self.page._schedule_redraw("theme")

        preview.assert_called_once()
        self.assertEqual("theme", preview.call_args.kwargs["reason"])
        self.assertGreater(preview.call_args.kwargs["total_points"], 10000)
        self.assertEqual("theme", self.page.render_diagnostics()["pending_reason"])
        start.assert_called_once()

    def test_render_diagnostics_capture_last_render_summary(self) -> None:
        self.page._record_render_summary(reason="data", mode="full", total_points=321, elapsed_ms=12.5)
        diagnostics = self.page.render_diagnostics()
        self.assertEqual("data", diagnostics["last_reason"])
        self.assertEqual("full", diagnostics["last_mode"])
        self.assertEqual(321, diagnostics["last_total_points"])
        self.assertAlmostEqual(12.5, diagnostics["last_elapsed_ms"])
