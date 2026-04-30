from __future__ import annotations

import unittest

from ui.page_view_state import SettingsPageViewState


class TestSettingsPageViewState(unittest.TestCase):
    def test_settings_page_view_state_defaults(self) -> None:
        state = SettingsPageViewState()
        self.assertFalse(state.extension_height_refresh_pending)
