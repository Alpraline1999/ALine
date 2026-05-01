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
        style = item_option.widget.style() if item_option.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, item_option, painter, item_option.widget)

        if index.data(Qt.ItemDataRole.CheckStateRole) is not None:
            self._drawCheckBox(painter, item_option, index)

        if item_option.state & (QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver):
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            self._drawBackground(painter, item_option, index)
            self._drawIndicator(painter, item_option, index)
            painter.restore()

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
        check_state = index.data(Qt.ItemDataRole.CheckStateRole)
        if check_state is None:
            return
        opt = QStyleOptionViewItem(item_option)
        opt.rect = QRectF(opt.rect).toRect()
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

    def _drawBackground(self, painter, item_option, index):
        """Draw selection or hover background."""
        opt = QStyleOptionViewItem(item_option)
        opt.rect = QRectF(opt.rect).toRect()
        if item_option.state & QStyle.StateFlag.State_Selected:
            color = item_option.palette.color(QPalette.ColorRole.Highlight)
            painter.setBrush(color)
            painter.drawRoundedRect(opt.rect.adjusted(2, 2, -2, -2), 4, 4)

    def _drawIndicator(self, painter, item_option, index):
        """Draw focus indicator."""
        if item_option.state & QStyle.StateFlag.State_HasFocus:
            opt = QStyleOptionViewItem(item_option)
            opt.rect = QRectF(opt.rect).toRect()
            color = item_option.palette.color(QPalette.ColorRole.Highlight)
            painter.setPen(color)
            painter.drawRoundedRect(opt.rect.adjusted(2, 2, -2, -2), 4, 4)
