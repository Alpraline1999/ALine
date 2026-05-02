"""
ProjectTreeWidget 自定义 delegate — 支持 wrap-anywhere 文本换行模式。
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QAbstractTextDocumentLayout,
    QPainter,
    QPalette,
    QTextDocument,
    QTextOption,
)
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionViewItem
from qfluentwidgets.components.widgets.tree_view import TreeItemDelegate


class ProjectTreeWrapAnywhereDelegate(TreeItemDelegate):
    """支持单词内任意位置换行的 tree item delegate。"""

    def __init__(self, owner, parent):
        super().__init__(parent)
        self._owner = owner

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        if self._owner._name_display_mode != "wrap":
            super().paint(painter, option, index)
            return

        item_option = QStyleOptionViewItem(option)
        self.initStyleOption(item_option, index)
        text = item_option.text
        if not text:
            super().paint(painter, option, index)
            return

        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        item_option.text = ""
        super().paint(painter, item_option, index)

        style = item_option.widget.style() if item_option.widget is not None else QApplication.style()
        text_rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, item_option, item_option.widget)
        if not text_rect.isValid() or text_rect.width() <= 0:
            return

        document = QTextDocument()
        document.setDefaultFont(item_option.font)
        text_option = QTextOption()
        text_option.setWrapMode(QTextOption.WrapMode.WrapAnywhere)
        text_option.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        document.setDefaultTextOption(text_option)
        document.setPlainText(text)
        document.setTextWidth(max(1, text_rect.width()))

        palette = QPalette(item_option.palette)
        foreground = index.data(Qt.ItemDataRole.ForegroundRole)
        if item_option.state & QStyle.StateFlag.State_Selected:
            text_color = palette.color(QPalette.ColorRole.HighlightedText)
        elif hasattr(foreground, "color"):
            text_color = foreground.color()
        else:
            text_color = palette.color(QPalette.ColorRole.Text)

        paint_context = QAbstractTextDocumentLayout.PaintContext()
        paint_context.palette = QPalette(palette)
        paint_context.palette.setColor(QPalette.ColorRole.Text, text_color)
        paint_context.palette.setColor(QPalette.ColorRole.WindowText, text_color)
        paint_context.palette.setColor(QPalette.ColorRole.HighlightedText, text_color)

        content_height = document.size().height()
        y_offset = text_rect.top() + max(0.0, (text_rect.height() - content_height) / 2.0)
        painter.save()
        painter.setClipRect(text_rect)
        painter.translate(text_rect.left(), y_offset)
        document.documentLayout().draw(painter, paint_context)
        painter.restore()

    def _drawCheckBox(self, painter, item_option, index):
        """Draw checkbox state for the item."""
        super()._drawCheckBox(painter, item_option, index)

    def _drawBackground(self, painter, item_option, index):
        """Draw selection or hover background."""
        super()._drawBackground(painter, item_option, index)

    def _drawIndicator(self, painter, item_option, index):
        """Draw focus indicator."""
        super()._drawIndicator(painter, item_option, index)
