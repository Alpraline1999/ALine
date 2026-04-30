from __future__ import annotations

import unittest

from app.workspaces.data_workspace import DataWorkspaceController, DataWorkspaceState


class TestDataWorkspace(unittest.TestCase):
    def test_controller_updates_tree_selection_state(self) -> None:
        state = DataWorkspaceState()
        controller = DataWorkspaceController(state)

        controller.handle_tree_selected("data_file", "node-1")

        self.assertEqual("data_file", state.selected_node_kind)
        self.assertEqual("node-1", state.selected_node_id)

    def test_controller_can_clear_selection(self) -> None:
        state = DataWorkspaceState(selected_type="series", selected_id="s1", selected_node_kind="series", selected_node_id="s1")
        controller = DataWorkspaceController(state)

        controller.clear_selection()

        self.assertIsNone(state.selected_type)
        self.assertIsNone(state.selected_id)
        self.assertIsNone(state.selected_node_kind)
        self.assertIsNone(state.selected_node_id)


if __name__ == "__main__":
    unittest.main()
