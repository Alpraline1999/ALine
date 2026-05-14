from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QWidget
from qfluentwidgets import MessageBoxBase, PlainTextEdit, SubtitleLabel


class NodeRemarkDialog(MessageBoxBase):
    def __init__(self, title: str, remark: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._title_label = SubtitleLabel(title, self.widget)
        self.viewLayout.addWidget(self._title_label)

        self._edit = PlainTextEdit(self.widget)
        self._edit.setPlainText(remark or "")
        self._edit.setPlaceholderText("输入备注")
        self._edit.setMinimumSize(560, 240)
        self.viewLayout.addWidget(self._edit)

        self.widget.setMinimumWidth(600)
        self.yesButton.setText("保存")
        self.cancelButton.setText("取消")

    def value(self) -> str:
        return self._edit.toPlainText().strip()

    @classmethod
    def get_remark(
        cls,
        parent,
        title: str,
        *,
        remark: str = "",
    ) -> tuple[str, bool]:
        dialog = cls(title, remark=remark, parent=parent)
        accepted = bool(dialog.exec())
        return dialog.value(), accepted
