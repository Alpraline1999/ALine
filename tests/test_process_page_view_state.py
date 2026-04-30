from __future__ import annotations

import unittest

from ui.page_view_state import ProcessPageViewState


class TestProcessPageViewState(unittest.TestCase):
    def test_process_page_view_state_defaults(self) -> None:
        state = ProcessPageViewState()
        self.assertFalse(state.extension_panel_visible)
        self.assertEqual(state.extension_panel_width, 360)
        self.assertFalse(state.selected_input_splitter_user_resized)
