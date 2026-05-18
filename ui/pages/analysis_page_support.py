from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QAbstractItemView, QWidget
from qfluentwidgets import (
    Action,
    FluentIcon as FIF,
    ListWidget,
    MessageBoxBase,
    RoundMenu,
    TableWidget,
    TabCloseButtonDisplayMode,
    ToolButton,
    CaptionLabel,
    SubtitleLabel,
    PlainTextEdit,
    isDarkTheme,
)
from ui.matplotlib_fonts import bootstrap_matplotlib_qtagg

_matplotlib, FigureCanvas, Figure, _MATPLOTLIB_ERROR = bootstrap_matplotlib_qtagg()
HAS_MATPLOTLIB = _matplotlib is not None

_PREFERRED_ANALYSIS_ORDER = (
    "curve_fit",
    "peak_detect",
    "statistics",
    "correlation",
    "error_compare",
    "curve_intersections",
    "area_between_curves",
    "lag_analysis",
)


class _SelectableResultTable(TableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection_to_clipboard()
            event.accept()
            return
        super().keyPressEvent(event)

    def copy_selection_to_clipboard(self) -> None:
        ranges = self.selectedRanges()
        if not ranges:
            return
        selected_range = ranges[0]
        rows: List[str] = []
        for row in range(selected_range.topRow(), selected_range.bottomRow() + 1):
            cells: List[str] = []
            for column in range(selected_range.leftColumn(), selected_range.rightColumn() + 1):
                item = self.item(row, column)
                cells.append("" if item is None else item.text())
            rows.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(rows))

    def _show_context_menu(self, pos) -> None:
        menu = RoundMenu(parent=self)
        copy_action = Action(FIF.COPY, "复制选中内容", self)
        copy_action.triggered.connect(self.copy_selection_to_clipboard)
        copy_action.setEnabled(bool(self.selectedRanges()))
        menu.addAction(copy_action)
        menu.exec(self.viewport().mapToGlobal(pos))


class _SelectableResultList(ListWidget):
    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection_to_clipboard()
            event.accept()
            return
        super().keyPressEvent(event)

    def copy_selection_to_clipboard(self) -> None:
        items = self.selectedItems()
        if not items:
            return
        QApplication.clipboard().setText("\n".join(item.text() for item in items))
