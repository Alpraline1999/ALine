from __future__ import annotations

from typing import Iterable, Optional

from qfluentwidgets import BodyLabel, ComboBox, LineEdit, MessageBoxBase, SubtitleLabel


class TextInputDialog(MessageBoxBase):
    def __init__(
        self,
        title: str,
        label: str = "",
        *,
        placeholder: str = "",
        text: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._title_label = SubtitleLabel(title, self.widget)
        self.viewLayout.addWidget(self._title_label)
        if label:
            self._body_label = BodyLabel(label, self.widget)
            self._body_label.setWordWrap(True)
            self.viewLayout.addWidget(self._body_label)
        else:
            self._body_label = None
        self._edit = LineEdit(self.widget)
        self._edit.setText(text)
        self._edit.setPlaceholderText(placeholder)
        self._edit.setClearButtonEnabled(True)
        self.viewLayout.addWidget(self._edit)
        self.widget.setMinimumWidth(360)

    def value(self) -> str:
        return self._edit.text()

    @classmethod
    def get_text(
        cls,
        parent,
        title: str,
        label: str = "",
        *,
        placeholder: str = "",
        text: str = "",
    ) -> tuple[str, bool]:
        dialog = cls(title, label, placeholder=placeholder, text=text, parent=parent)
        accepted = bool(dialog.exec())
        return dialog.value(), accepted


class SelectionDialog(MessageBoxBase):
    def __init__(
        self,
        title: str,
        label: str,
        options: Iterable[str],
        *,
        current_text: Optional[str] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._title_label = SubtitleLabel(title, self.widget)
        self._body_label = BodyLabel(label, self.widget)
        self._body_label.setWordWrap(True)
        self._combo = ComboBox(self.widget)
        for option in options:
            self._combo.addItem(option)
        if current_text:
            index = self._combo.findText(current_text)
            if index >= 0:
                self._combo.setCurrentIndex(index)
        self.viewLayout.addWidget(self._title_label)
        self.viewLayout.addWidget(self._body_label)
        self.viewLayout.addWidget(self._combo)
        self.widget.setMinimumWidth(360)

    def value(self) -> str:
        return self._combo.currentText().strip()

    @classmethod
    def get_item(
        cls,
        parent,
        title: str,
        label: str,
        options: Iterable[str],
        *,
        current_text: Optional[str] = None,
    ) -> tuple[str, bool]:
        dialog = cls(title, label, options, current_text=current_text, parent=parent)
        accepted = bool(dialog.exec())
        return dialog.value(), accepted