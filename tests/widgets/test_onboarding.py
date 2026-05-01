"""PageOnboardingController — 从 test_ui.py 提取。"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from PySide6.QtWidgets import QApplication
from tests.ui_test_helpers import setUpModule, tearDownModule  # noqa: F401


class TestPageOnboardingController(unittest.TestCase):

    def test_controller_uses_end_prev_next_buttons_in_one_flow(self):
        from PySide6.QtWidgets import QWidget
        from qfluentwidgets import PrimaryPushButton, PushButton, TeachingTipTailPosition
        from ui.widgets.onboarding import OnboardingStep, PageOnboardingController

        host = QWidget()
        target = QWidget(host)
        host.show()
        QApplication.processEvents()
        captured = {}

        class _FakeTip:
            def close(self):
                return None

        def _fake_make(view, tip_target, duration, tail_position, parent):
            captured["target"] = tip_target
            captured["tail_position"] = tail_position
            captured["parent"] = parent
            buttons = [button for button in view.findChildren(PushButton) if button.text()]
            captured["push_buttons"] = sorted(button.text() for button in buttons)
            captured["button_parent_ids"] = {id(button.parentWidget()) for button in buttons}
            captured["primary_buttons"] = [
                button.text() for button in view.findChildren(PrimaryPushButton) if button.text()
            ]
            return _FakeTip()

        controller = PageOnboardingController(
            host,
            "test-onboarding",
            lambda: [
                OnboardingStep(
                    lambda: target,
                    TeachingTipTailPosition.BOTTOM,
                    "标题",
                    "内容",
                )
            ],
            is_completed=lambda: False,
            mark_completed=lambda completed: completed,
        )

        with mock.patch("ui.widgets.onboarding.TeachingTip.make", side_effect=_fake_make):
            controller.start(force=True)

        self.assertCountEqual(captured["push_buttons"], ["上一步", "结束引导", "下一步"])
        self.assertEqual(captured["primary_buttons"], ["下一步"])
        self.assertEqual(len(captured["button_parent_ids"]), 1)
        self.assertIs(captured["target"], target)
        self.assertIs(captured["parent"], host)
        target.deleteLater()
        host.deleteLater()
