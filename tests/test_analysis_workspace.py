from __future__ import annotations

import unittest

from app.workspaces.analysis_workspace import AnalysisWorkspaceController, AnalysisWorkspaceState


class TestAnalysisWorkspace(unittest.TestCase):
    def test_controller_updates_tree_selection_state(self) -> None:
        state = AnalysisWorkspaceState()
        controller = AnalysisWorkspaceController(state)

        controller.handle_tree_selected("series", "s1")

        self.assertEqual("series", state.selected_tree_kind)
        self.assertEqual("s1", state.selected_tree_node_id)

    def test_controller_normalizes_analysis_suffix(self) -> None:
        state = AnalysisWorkspaceState()
        controller = AnalysisWorkspaceController(state)

        handled = controller.handle_tree_activated("curve_to_analysis", "c1")

        self.assertEqual(("curve", "c1"), handled)


if __name__ == "__main__":
    unittest.main()
