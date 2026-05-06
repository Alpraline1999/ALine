from __future__ import annotations

from enum import Enum
from typing import Optional

from PySide6.QtWidgets import QHBoxLayout, QWidget
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

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)
        button_row.addStretch()

        save_btn = PrimaryPushButton("保存", self.widget)
        save_btn.clicked.connect(self._accept_save)
        button_row.addWidget(save_btn)

        discard_btn = PushButton("不保存", self.widget)
        discard_btn.clicked.connect(self._accept_discard)
        button_row.addWidget(discard_btn)

        cancel_btn = PushButton("取消", self.widget)
        cancel_btn.clicked.connect(self._reject_cancel)
        button_row.addWidget(cancel_btn)

        self.viewLayout.addLayout(button_row)
        self.widget.setMinimumWidth(420)

        self.yesButton.hide()
        self.cancelButton.hide()

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
