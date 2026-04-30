from __future__ import annotations

import unittest

from ui.page_view_state import AnalysisPageViewState, ChartPageViewState, DigitizePageViewState


class TestPageViewState(unittest.TestCase):
    def test_chart_page_view_state_defaults(self) -> None:
        state = ChartPageViewState()
        self.assertFalse(state.extension_panel_visible)
        self.assertFalse(state.chart_left_splitter_user_resized)
        self.assertFalse(state.chart_list_tooltip_visible)

    def test_analysis_page_view_state_defaults(self) -> None:
        state = AnalysisPageViewState()
        self.assertFalse(state.extension_panel_visible)
        self.assertFalse(state.input_panel_splitter_user_resized)

    def test_digitize_page_view_state_defaults(self) -> None:
        state = DigitizePageViewState()
        self.assertFalse(state.extension_panel_visible)
        self.assertFalse(state.right_splitter_initialized)
        self.assertFalse(state.right_splitter_user_resized)
