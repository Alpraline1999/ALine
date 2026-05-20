"""Dialog focus commit — 从 test_ui.py 提取。"""
from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from PySide6.QtWidgets import QApplication, QLineEdit, QWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from tests.ui_test_helpers import setUpModule, tearDownModule  # noqa: F401


class TestDialogFocusCommit(unittest.TestCase):
    def test_click_away_focus_commit(self):
        from ui.widgets.focus_commit import install_click_away_focus_commit
        host = QWidget()
        host.resize(400, 100)
        edit1 = QLineEdit(host)
        edit1.move(10, 10)
        edit1.resize(100, 30)
        edit2 = QLineEdit(host)
        edit2.move(10, 50)
        edit2.resize(100, 30)
        edit1.setText("old")
        host.show()
        QApplication.processEvents()

        install_click_away_focus_commit(host)
        edit1.setFocus()
        self.assertTrue(edit1.hasFocus())
        QTest.mouseClick(edit2, Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        self.assertFalse(edit1.hasFocus(), "clicking away should clear focus from the editor")
        host.deleteLater()
