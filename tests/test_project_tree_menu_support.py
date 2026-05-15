from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentIcon as FIF, RoundMenu

from ui.widgets.project_tree_support import add_menu_action


_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication(sys.argv)


class TestProjectTreeMenuSupport(unittest.TestCase):
    def test_add_menu_action_accepts_zero_argument_callback(self) -> None:
        calls: list[str] = []
        menu = RoundMenu()

        action = add_menu_action(menu, FIF.FOLDER, "测试动作", lambda: calls.append("triggered"))
        action.trigger()

        self.assertEqual(calls, ["triggered"])


if __name__ == "__main__":
    unittest.main()
