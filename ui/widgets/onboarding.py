from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QWidget
from qfluentwidgets import (
    InfoBarIcon,
    PrimaryPushButton,
    PushButton,
    TeachingTip,
    TeachingTipTailPosition,
    TeachingTipView,
)

from core.ui_preferences import is_page_onboarding_completed, set_page_onboarding_completed


@dataclass(frozen=True)
class OnboardingStep:
    target_getter: Callable[[], Optional[QWidget]]
    tail_position: TeachingTipTailPosition
    title: str
    content: str


class PageOnboardingController:
    def __init__(
        self,
        owner: QWidget,
        page_key: str,
        steps_provider: Callable[[], List[OnboardingStep]],
        *,
        delay_ms: int = 180,
        is_completed: Optional[Callable[[], bool]] = None,
        mark_completed: Optional[Callable[[bool], bool]] = None,
    ) -> None:
        self._owner = owner
        self._page_key = page_key.strip().lower()
        self._steps_provider = steps_provider
        self._delay_ms = max(0, int(delay_ms))
        self._is_completed = is_completed or (lambda: is_page_onboarding_completed(self._page_key))
        self._mark_completed = mark_completed or (lambda completed: set_page_onboarding_completed(self._page_key, completed))
        self._tip = None
        self._scheduled = False

    def schedule_auto_start(self) -> None:
        if self._scheduled or self._is_completed():
            return
        self._scheduled = True
        QTimer.singleShot(self._delay_ms, self._start_auto)

    def start(self, force: bool = False) -> None:
        if not force and self._is_completed():
            return
        if not self._owner.isVisible():
            self._scheduled = True
            QTimer.singleShot(self._delay_ms, lambda: self.start(force=force))
            return
        if not force:
            self._mark_completed(True)
        self._show_step(0)

    def close(self) -> None:
        if self._tip is not None:
            tip = self._tip
            self._tip = None
            tip.close()

    def _start_auto(self) -> None:
        self._scheduled = False
        if not self._owner.isVisible() or self._is_completed():
            return
        self.start(force=False)

    def _steps(self) -> List[OnboardingStep]:
        return [step for step in self._steps_provider() if step.target_getter() is not None]

    def _show_step(self, index: int) -> None:
        steps = self._steps()
        if index >= len(steps):
            self.close()
            return

        step = steps[index]
        target = step.target_getter()
        if target is None:
            self.close()
            return

        self.close()
        view = TeachingTipView(
            title=step.title,
            content=step.content,
            icon=InfoBarIcon.INFORMATION,
            isClosable=True,
            tailPosition=step.tail_position,
        )

        end_btn = PushButton("结束引导", view)
        end_btn.clicked.connect(self.close)
        view.addWidget(end_btn, align=Qt.AlignmentFlag.AlignRight)

        prev_btn = PushButton("上一步", view)
        prev_btn.setEnabled(index > 0)
        prev_btn.clicked.connect(lambda: self._show_step(max(0, index - 1)))
        view.addWidget(prev_btn, align=Qt.AlignmentFlag.AlignRight)

        next_btn = PrimaryPushButton("下一步", view)
        if index < len(steps) - 1:
            next_btn.clicked.connect(lambda: self._show_step(index + 1))
        else:
            next_btn.clicked.connect(self.close)
        view.addWidget(next_btn, align=Qt.AlignmentFlag.AlignRight)

        self._tip = TeachingTip.make(view, target, -1, step.tail_position, self._owner)
        view.closed.connect(self.close)