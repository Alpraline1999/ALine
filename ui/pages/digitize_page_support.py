from __future__ import annotations

from PySide6.QtWidgets import QWidget
from qfluentwidgets import LineEdit, MessageBoxBase, SubtitleLabel


_SUPPORTED_SOURCE_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}


class _InputDialog(MessageBoxBase):
    """输入对话框（替代 QInputDialog.getText）"""

    def __init__(self, title: str, placeholder: str = '', text: str = '', parent=None):
        super().__init__(parent)
        self._title_lbl = SubtitleLabel(title, self.widget)
        self._edit = LineEdit(self.widget)
        self._edit.setText(text)
        self._edit.setPlaceholderText(placeholder)
        self._edit.setClearButtonEnabled(True)
        self.viewLayout.addWidget(self._title_lbl)
        self.viewLayout.addWidget(self._edit)
        self.widget.setMinimumWidth(350)

    def value(self) -> str:
        return self._edit.text()
