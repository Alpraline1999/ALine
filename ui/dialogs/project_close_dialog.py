from __future__ import annotations

from enum import Enum
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from qfluentwidgets import BodyLabel, MessageBoxBase, PrimaryPushButton, PushButton, SubtitleLabel


class ProjectCloseDecision(str, Enum):
    SAVE = "save"
    DISCARD = "discard"
    CANCEL = "cancel"


class UnsavedProjectCloseDialog(MessageBoxBase):
    def __init__(self, project_name: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._decision = ProjectCloseDecision.CANCEL

        title = SubtitleLabel("项目已修改", self.widget)
        title.setWordWrap(True)
        self.viewLayout.addWidget(title)

        message = BodyLabel(
            f"当前项目「{project_name}」有未保存的更改。\n关闭前请选择操作。",
            self.widget,
        )
        message.setWordWrap(True)
        self.viewLayout.addWidget(message)

        self.widget.setMinimumWidth(420)

        self.yesButton.setText("保存")
        self.cancelButton.setText("不保存")
        self.yesButton.clicked.connect(self._accept_save)
        self.cancelButton.clicked.connect(self._accept_discard)

        self._extra_cancel_button = PushButton("取消", self.buttonGroup)
        self._extra_cancel_button.setAttribute(Qt.WA_LayoutUsesWidgetRect)
        self._extra_cancel_button.clicked.connect(self._reject_cancel)
        self.buttonLayout.addWidget(self._extra_cancel_button, 1, Qt.AlignmentFlag.AlignVCenter)

    def _accept_save(self) -> None:
        self._decision = ProjectCloseDecision.SAVE
        self.accept()

    def _accept_discard(self) -> None:
        self._decision = ProjectCloseDecision.DISCARD
        self.accept()

    def _reject_cancel(self) -> None:
        self._decision = ProjectCloseDecision.CANCEL
        self.reject()

    @property
    def decision(self) -> ProjectCloseDecision:
        return self._decision


def confirm_unsaved_project_close(project_name: str, parent: Optional[QWidget] = None) -> ProjectCloseDecision:
    dialog = UnsavedProjectCloseDialog(project_name, parent)
    dialog.exec()
    return dialog.decision
