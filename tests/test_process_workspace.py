from __future__ import annotations

import unittest

from app.workspaces.process_workspace import ProcessWorkspaceController, ProcessWorkspaceState


class TestProcessWorkspace(unittest.TestCase):
    def test_receive_data_request_updates_selected_source_state(self) -> None:
        state = ProcessWorkspaceState()
        controller = ProcessWorkspaceController(state)

        controller.receive_data_request("series", "s1")

        self.assertEqual("series", state.selected_source_kind)
        self.assertEqual("s1", state.selected_source_node_id)

    def test_handle_tree_activated_normalizes_process_suffix(self) -> None:
        state = ProcessWorkspaceState()
        controller = ProcessWorkspaceController(state)

        handled = controller.handle_tree_activated("curve_to_process", "c1")

        self.assertEqual(("curve", "c1"), handled)
        self.assertEqual("curve", state.selected_source_kind)
        self.assertEqual("c1", state.selected_source_node_id)


if __name__ == "__main__":
    unittest.main()
