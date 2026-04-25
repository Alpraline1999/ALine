from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import FluentIcon as FIF, ToolButton

try:
    from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
except Exception:  # pragma: no cover - matplotlib 不可用时退化
    NavigationToolbar = None


@dataclass
class PreviewToolbarButtons:
    fit: ToolButton
    zoom_in: ToolButton
    zoom_out: ToolButton
    pan: ToolButton
    box_zoom: ToolButton


def create_navigation_toolbar(canvas, parent: QWidget):
    if canvas is None or NavigationToolbar is None:
        return None
    toolbar = NavigationToolbar(canvas, parent)
    toolbar.hide()
    return toolbar


def build_preview_toolbar(
    parent: QWidget,
    *,
    button_size: int,
    reset_callback: Callable[[], None],
    zoom_in_callback: Callable[[], None],
    zoom_out_callback: Callable[[], None],
    pan_toggle_callback: Callable[[bool], None],
    box_zoom_toggle_callback: Callable[[bool], None],
    install_tooltip: Optional[Callable[[ToolButton, str], None]] = None,
) -> tuple[QHBoxLayout, PreviewToolbarButtons]:
    layout = QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)

    fit_btn = ToolButton(getattr(FIF, "FIT_PAGE", FIF.HOME), parent)
    fit_btn.setToolTip("重置预览范围")
    fit_btn.clicked.connect(reset_callback)
    fit_btn.setFixedSize(button_size, button_size)
    layout.addWidget(fit_btn)

    zoom_in_btn = ToolButton(getattr(FIF, "ZOOM_IN", FIF.ZOOM), parent)
    zoom_in_btn.setToolTip("放大预览")
    zoom_in_btn.clicked.connect(zoom_in_callback)
    zoom_in_btn.setFixedSize(button_size, button_size)
    layout.addWidget(zoom_in_btn)

    zoom_out_btn = ToolButton(getattr(FIF, "ZOOM_OUT", FIF.ZOOM), parent)
    zoom_out_btn.setToolTip("缩小预览")
    zoom_out_btn.clicked.connect(zoom_out_callback)
    zoom_out_btn.setFixedSize(button_size, button_size)
    layout.addWidget(zoom_out_btn)

    pan_btn = ToolButton(getattr(FIF, "MOVE", getattr(FIF, "MOVE_TO", FIF.ZOOM)), parent)
    pan_btn.setToolTip("拖拽平移预览")
    pan_btn.setCheckable(True)
    pan_btn.toggled.connect(pan_toggle_callback)
    pan_btn.setFixedSize(button_size, button_size)
    layout.addWidget(pan_btn)

    box_zoom_btn = ToolButton(FIF.ZOOM, parent)
    box_zoom_btn.setToolTip("框选局部放大")
    box_zoom_btn.setCheckable(True)
    box_zoom_btn.toggled.connect(box_zoom_toggle_callback)
    box_zoom_btn.setFixedSize(button_size, button_size)
    layout.addWidget(box_zoom_btn)
    layout.addStretch(1)

    if install_tooltip is not None:
        for button in (fit_btn, zoom_in_btn, zoom_out_btn, pan_btn, box_zoom_btn):
            install_tooltip(button, button.toolTip())

    return layout, PreviewToolbarButtons(
        fit=fit_btn,
        zoom_in=zoom_in_btn,
        zoom_out=zoom_out_btn,
        pan=pan_btn,
        box_zoom=box_zoom_btn,
    )


def preview_navigation_mode(toolbar) -> str:
    if toolbar is None:
        return ""
    mode = getattr(toolbar, "mode", None)
    mode_name = str(getattr(mode, "name", mode or "")).strip().lower()
    if "zoom" in mode_name:
        return "zoom"
    if "pan" in mode_name:
        return "pan"
    return ""


def sync_preview_nav_toggle_states(toolbar, pan_button: Optional[ToolButton], box_zoom_button: Optional[ToolButton]) -> None:
    mode = preview_navigation_mode(toolbar)
    for button, active in ((pan_button, mode == "pan"), (box_zoom_button, mode == "zoom")):
        if button is None:
            continue
        blocker = QSignalBlocker(button)
        button.setChecked(active)
        del blocker


def toggle_preview_pan_mode(toolbar, pan_button: Optional[ToolButton], box_zoom_button: Optional[ToolButton], checked: bool) -> None:
    if toolbar is None:
        return
    current_mode = preview_navigation_mode(toolbar)
    if checked:
        if current_mode == "zoom":
            toolbar.zoom()
        if preview_navigation_mode(toolbar) != "pan":
            toolbar.pan()
    elif current_mode == "pan":
        toolbar.pan()
    sync_preview_nav_toggle_states(toolbar, pan_button, box_zoom_button)


def toggle_preview_box_zoom_mode(toolbar, pan_button: Optional[ToolButton], box_zoom_button: Optional[ToolButton], checked: bool) -> None:
    if toolbar is None:
        return
    current_mode = preview_navigation_mode(toolbar)
    if checked:
        if current_mode == "pan":
            toolbar.pan()
        if preview_navigation_mode(toolbar) != "zoom":
            toolbar.zoom()
    elif current_mode == "zoom":
        toolbar.zoom()
    sync_preview_nav_toggle_states(toolbar, pan_button, box_zoom_button)


def zoom_figure_axes(figure, canvas, factor: float, *, redraw_callback: Optional[Callable[[], None]] = None) -> None:
    if figure is None or canvas is None:
        return
    axes = list(figure.axes)
    if not axes and redraw_callback is not None:
        redraw_callback()
        axes = list(figure.axes)
    if not axes:
        return
    for axis in axes:
        x0, x1 = axis.get_xlim()
        y0, y1 = axis.get_ylim()
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        half_x = abs(x1 - x0) * factor / 2.0
        half_y = abs(y1 - y0) * factor / 2.0
        if half_x == 0:
            half_x = 0.5
        if half_y == 0:
            half_y = 0.5
        axis.set_xlim(cx - half_x, cx + half_x)
        axis.set_ylim(cy - half_y, cy + half_y)
    canvas.draw_idle()