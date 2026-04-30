from __future__ import annotations

import unittest

from app.workspaces.digitize_workspace import DigitizeWorkspaceController, DigitizeWorkspaceState


class TestDigitizeWorkspace(unittest.TestCase):
    def test_controller_updates_current_selection_state(self) -> None:
        state = DigitizeWorkspaceState()
        controller = DigitizeWorkspaceController(state)

        controller.set_current_image("img-1")
        controller.set_current_curve("curve-1")
        controller.set_export_target("data_file", "node-1")

        self.assertEqual("img-1", state.current_image_id)
        self.assertEqual("curve-1", state.current_curve_id)
        self.assertEqual("data_file", state.export_target_kind)
        self.assertEqual("node-1", state.export_target_id)

    def test_controller_can_clear_pending_interaction(self) -> None:
        state = DigitizeWorkspaceState(pending_digitize_field_key="sampled_color", pending_digitize_field_type="pickcolor")
        controller = DigitizeWorkspaceController(state)

        controller.clear_pending_interaction()

        self.assertIsNone(state.pending_digitize_field_key)
        self.assertIsNone(state.pending_digitize_field_type)


if __name__ == "__main__":
    unittest.main()
