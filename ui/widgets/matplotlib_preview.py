from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import QEvent, QObject, QSignalBlocker, QPointF, Qt
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import FluentIcon as FIF, ToggleToolButton, ToolButton, ToolTipPosition

from ui.theme import install_fluent_tooltip

try:
    from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
except Exception:  # pragma: no cover - matplotlib 不可用时退化
    NavigationToolbar = None


@dataclass
class PreviewToolbarButtons:
    fit: ToolButton
    zoom_in: ToolButton
    zoom_out: ToolButton
    pan: ToggleToolButton
    box_zoom: ToggleToolButton


class _PreviewGestureFilter(QObject):
    def __init__(self, toolbar, sync_callback: Optional[Callable[[], None]], parent: Optional[QObject] = None):
        super().__init__(parent)
        self._toolbar = toolbar
        self._sync_callback = sync_callback
        self._active_mode: str = ""
        self._active_axis = None
        self._press_pos: Optional[QPointF] = None
        self._press_xlim: tuple[float, float] | None = None
        self._press_ylim: tuple[float, float] | None = None

    @staticmethod
    def _event_pos(event) -> QPointF:
        if hasattr(event, "position"):
            return event.position()
        pos = event.pos()
        return QPointF(float(pos.x()), float(pos.y()))

    def _sync(self) -> None:
        if callable(self._sync_callback):
            self._sync_callback()

    @staticmethod
    def _axis_at(canvas, pos: QPointF):
        figure = getattr(canvas, "figure", None)
        if figure is None:
            return None
        for axis in figure.axes:
            try:
                if axis.bbox.contains(pos.x(), pos.y()):
                    return axis
            except Exception:
                continue
        return None

    @staticmethod
    def _zoom_axis(axis, center_x: float, center_y: float, factor: float) -> None:
        x0, x1 = axis.get_xlim()
        y0, y1 = axis.get_ylim()
        width = abs(x1 - x0) * factor
        height = abs(y1 - y0) * factor
        if width == 0:
            width = 1.0
        if height == 0:
            height = 1.0
        axis.set_xlim(center_x - width / 2.0, center_x + width / 2.0)
        axis.set_ylim(center_y - height / 2.0, center_y + height / 2.0)

    def _reset(self) -> bool:
        if self._toolbar is None:
            return False
        reset = getattr(self._toolbar, "home", None)
        if callable(reset):
            reset()
            self._sync()
            return True
        return False

    def _clear_toolbar_mode(self) -> None:
        mode = preview_navigation_mode(self._toolbar)
        if mode == "pan":
            self._toolbar.pan()
        elif mode == "zoom":
            self._toolbar.zoom()

    def _pan_axis(self, axis, start_pos: QPointF, current_pos: QPointF) -> None:
        start_data = axis.transData.inverted().transform((start_pos.x(), start_pos.y()))
        current_data = axis.transData.inverted().transform((current_pos.x(), current_pos.y()))
        dx = float(start_data[0] - current_data[0])
        dy = float(start_data[1] - current_data[1])
        x0, x1 = self._press_xlim or axis.get_xlim()
        y0, y1 = self._press_ylim or axis.get_ylim()
        axis.set_xlim(x0 + dx, x1 + dx)
        axis.set_ylim(y0 + dy, y1 + dy)

    def _box_zoom_axis(self, axis, start_pos: QPointF, end_pos: QPointF) -> None:
        start_data = axis.transData.inverted().transform((start_pos.x(), start_pos.y()))
        end_data = axis.transData.inverted().transform((end_pos.x(), end_pos.y()))
        x0, x1 = float(start_data[0]), float(end_data[0])
        y0, y1 = float(start_data[1]), float(end_data[1])
        if abs(x0 - x1) < 1e-9 or abs(y0 - y1) < 1e-9:
            return
        axis.set_xlim(min(x0, x1), max(x0, x1))
        axis.set_ylim(min(y0, y1), max(y0, y1))

    def eventFilter(self, watched, event) -> bool:
        if self._toolbar is None:
            return False
        if event.type() == QEvent.Type.Wheel:
            pos = self._event_pos(event)
            axis = self._axis_at(watched, pos)
            if axis is None:
                return False
            delta = event.angleDelta().y() if hasattr(event, "angleDelta") else 0
            if delta == 0:
                return False
            try:
                center_x, center_y = axis.transData.inverted().transform((pos.x(), pos.y()))
            except Exception:
                return False
            self._zoom_axis(axis, float(center_x), float(center_y), 0.8 if delta > 0 else 1.25)
            watched.draw_idle()
            self._sync()
            return True
        if event.type() == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.RightButton:
            return self._reset()
        if event.type() == QEvent.Type.MouseButtonPress:
            pos = self._event_pos(event)
            axis = self._axis_at(watched, pos)
            if axis is None:
                return False
            self._clear_toolbar_mode()
            if event.button() == Qt.MouseButton.RightButton:
                self._active_mode = "pan"
                self._active_axis = axis
                self._press_pos = pos
                self._press_xlim = axis.get_xlim()
                self._press_ylim = axis.get_ylim()
                return True
            if event.button() == Qt.MouseButton.LeftButton:
                self._active_mode = "zoom"
                self._active_axis = axis
                self._press_pos = pos
                self._press_xlim = axis.get_xlim()
                self._press_ylim = axis.get_ylim()
                return True
            return False
        if event.type() == QEvent.Type.MouseMove:
            if self._active_axis is None or self._press_pos is None:
                return False
            if event.buttons() & Qt.MouseButton.RightButton and self._active_mode == "pan":
                self._pan_axis(self._active_axis, self._press_pos, self._event_pos(event))
                watched.draw_idle()
                self._sync()
                return True
            return False
        if event.type() == QEvent.Type.MouseButtonRelease:
            if self._active_axis is None or self._press_pos is None:
                return False
            if self._active_mode == "zoom" and event.button() == Qt.MouseButton.LeftButton:
                self._box_zoom_axis(self._active_axis, self._press_pos, self._event_pos(event))
                watched.draw_idle()
                self._sync()
                self._active_axis = None
                self._active_mode = ""
                self._press_pos = None
                self._press_xlim = None
                self._press_ylim = None
                return True
            if self._active_mode == "pan" and event.button() == Qt.MouseButton.RightButton:
                self._active_axis = None
                self._active_mode = ""
                self._press_pos = None
                self._press_xlim = None
                self._press_ylim = None
                self._sync()
                return True
        return False


def create_navigation_toolbar(canvas, parent: QWidget, *, sync_callback: Optional[Callable[[], None]] = None):
    if canvas is None or NavigationToolbar is None:
        return None
    toolbar = NavigationToolbar(canvas, parent)
    toolbar.hide()
    gesture_filter = _PreviewGestureFilter(toolbar, sync_callback, canvas)
    canvas.installEventFilter(gesture_filter)
    setattr(canvas, "_preview_gesture_filter", gesture_filter)
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
    tooltip_delay: int = 300,
    tooltip_position=ToolTipPosition.BOTTOM,
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

    pan_btn = ToggleToolButton(getattr(FIF, "MOVE", getattr(FIF, "MOVE_TO", FIF.ZOOM)), parent)
    pan_btn.setToolTip("拖拽平移预览")
    pan_btn.toggled.connect(pan_toggle_callback)
    pan_btn.setFixedSize(button_size, button_size)
    layout.addWidget(pan_btn)

    box_zoom_btn = ToggleToolButton(FIF.ZOOM, parent)
    box_zoom_btn.setToolTip("框选局部放大")
    box_zoom_btn.toggled.connect(box_zoom_toggle_callback)
    box_zoom_btn.setFixedSize(button_size, button_size)
    layout.addWidget(box_zoom_btn)
    layout.addStretch(1)

    def _default_install_tooltip(widget: ToolButton, text: str) -> None:
        widget.setToolTip(text)
        install_fluent_tooltip(widget, delay=tooltip_delay, position=tooltip_position)

    tooltip_installer = install_tooltip or _default_install_tooltip
    for button in (fit_btn, zoom_in_btn, zoom_out_btn, pan_btn, box_zoom_btn):
        tooltip_installer(button, button.toolTip())

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
