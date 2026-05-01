"""
ImageViewer 工具栏与 UI 辅助。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget
from qfluentwidgets import Action, FluentIcon as FIF, ToolButton, TransparentToolButton


def build_toolbar_button(icon, tooltip: str, parent: QWidget = None) -> ToolButton:
    """创建一个标准的工具栏图标按钮。"""
    btn = TransparentToolButton(icon, parent)
    btn.setToolTip(tooltip)
    btn.setFixedSize(32, 32)
    btn.setIconSize(btn.size())
    return btn


def create_toolbar_layout(parent: QWidget = None) -> QHBoxLayout:
    """创建一个标准的工具栏水平布局。"""
    layout = QHBoxLayout()
    layout.setContentsMargins(4, 2, 4, 2)
    layout.setSpacing(2)
    layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
    return layout


TOOLBAR_ACTIONS = {
    "open": (FIF.PHOTO, "打开图片"),
    "fit": (FIF.ZOOM_FIT, "适应窗口"),
    "zoom_in": (FIF.ZOOM_IN, "放大"),
    "zoom_out": (FIF.ZOOM_OUT, "缩小"),
    "original": (getattr(FIF, "ACTUAL_SIZE", FIF.ZOOM_FIT), "原始大小"),
    "rotate_left": (getattr(FIF, "ROTATE", FIF.SYNC), "向左旋转"),
    "rotate_right": (getattr(FIF, "ROTATE", FIF.SYNC), "向右旋转"),
    "flip_h": (getattr(FIF, "MIRROR", FIF.VIEW), "水平翻转"),
    "flip_v": (getattr(FIF, "MIRROR", FIF.VIEW), "垂直翻转"),
    "save": (FIF.SAVE, "保存"),
    "save_as": (FIF.SAVE_AS, "另存为"),
}
