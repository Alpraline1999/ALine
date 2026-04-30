from __future__ import annotations

import unittest

from ui.page_view_state import MainWindowViewState


class TestMainWindowViewState(unittest.TestCase):
    def test_main_window_view_state_defaults(self) -> None:
        state = MainWindowViewState()
        self.assertFalse(state.tree_panel_user_hidden)
        self.assertEqual(state.tree_panel_width, 260)
        self.assertFalse(state.shared_extension_panel_visible)
