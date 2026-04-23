from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QAbstractSpinBox, QLineEdit, QPlainTextEdit, QTextEdit, QWidget


def _is_commit_editor(widget) -> bool:
    return isinstance(widget, (QLineEdit, QPlainTextEdit, QTextEdit, QAbstractSpinBox))


class ClickAwayFocusCommitFilter(QObject):
    def __init__(self, root: QWidget) -> None:
        super().__init__(root)
        self._root = root
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if event.type() != QEvent.Type.MouseButtonPress:
            return False
        target = watched if isinstance(watched, QWidget) else None
        if target is None:
            return False
        root = self._root
        if root is None or (target is not root and not root.isAncestorOf(target)):
            return False
        app = QApplication.instance()
        focus_widget = app.focusWidget() if app is not None else None
        if not _is_commit_editor(focus_widget):
            return False
        if target is focus_widget or focus_widget.isAncestorOf(target):
            return False
        focus_widget.clearFocus()
        return False


def install_click_away_focus_commit(root: QWidget) -> ClickAwayFocusCommitFilter:
    return ClickAwayFocusCommitFilter(root)