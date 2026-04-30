from __future__ import annotations

import unittest

from app.workspaces.chart_workspace import ChartWorkspaceController, ChartWorkspaceState


class TestChartWorkspace(unittest.TestCase):
    def test_controller_updates_tree_selection_state(self) -> None:
        state = ChartWorkspaceState()
        controller = ChartWorkspaceController(state)

        controller.handle_tree_selected("picture", "p1")

        self.assertEqual("picture", state.selected_tree_kind)
        self.assertEqual("p1", state.selected_tree_id)

    def test_controller_can_clear_series_selection(self) -> None:
        state = ChartWorkspaceState(style_target="curve-1")
        controller = ChartWorkspaceController(state)

        controller.clear_series_selection()

        self.assertIsNone(state.style_target)


if __name__ == "__main__":
    unittest.main()
