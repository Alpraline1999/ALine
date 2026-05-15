from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import QEvent, QObject, QSignalBlocker, QPointF, Qt
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import FluentIcon as FIF, ToggleToolButton, ToolButton, ToolTipPosition

from ui.theme import install_fluent_tooltip

try:
    from matplotlib.backend_bases import MouseButton, MouseEvent
    from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
except Exception:  # pragma: no cover - matplotlib 不可用时退化
    MouseButton = None
    MouseEvent = None
    NavigationToolbar = None


@dataclass
class PreviewToolbarButtons:
    fit: ToolButton
    zoom_in: ToolButton
    zoom_out: ToolButton
    pan: ToggleToolButton
    box_zoom: ToggleToolButton


class _PreviewGestureFilter(QObject):
    def __init__(
        self,
        toolbar,
        sync_callback: Optional[Callable[[], None]],
        *,
        reset_callback: Optional[Callable[[], None]] = None,
        zoom_in_callback: Optional[Callable[[], None]] = None,
        zoom_out_callback: Optional[Callable[[], None]] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._toolbar = toolbar
        self._sync_callback = sync_callback
        self._reset_callback = reset_callback
        self._zoom_in_callback = zoom_in_callback
        self._zoom_out_callback = zoom_out_callback
        self._active_mode: str = ""
        self._temporary_mode: str = ""
        self._buttons: Optional[PreviewToolbarButtons] = None

    def set_buttons(self, buttons: PreviewToolbarButtons) -> None:
        self._buttons = buttons

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

    def _reset(self) -> bool:
        if self._buttons is not None:
            self._buttons.fit.click()
            self._sync()
            return True
        if callable(self._reset_callback):
            self._reset_callback()
            self._sync()
            return True
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

    def _build_mouse_event(self, canvas, event_name: str, pos: QPointF, *, button=None, gui_event=None):
        if canvas is None or MouseEvent is None:
            return None
        if gui_event is not None and hasattr(canvas, "mouseEventCoords"):
            x, y = canvas.mouseEventCoords(gui_event)
        else:
            x, y = pos.x(), pos.y()
        return MouseEvent(
            event_name,
            canvas,
            x,
            y,
            button=button,
            key=None,
            step=0,
            dblclick=False,
            guiEvent=gui_event,
        )

    def _activate_toolbar_mode(self, mode: str) -> None:
        current_mode = preview_navigation_mode(self._toolbar)
        if mode == current_mode:
            return
        if current_mode:
            self._clear_toolbar_mode()
        if mode == "pan":
            self._toolbar.pan()
        elif mode == "zoom":
            self._toolbar.zoom()
        self._sync()

    def _toggle_button_for_mode(self, mode: str, checked: bool) -> None:
        if self._buttons is None:
            return
        button = self._buttons.pan if mode == "pan" else self._buttons.box_zoom
        if bool(button.isChecked()) == checked:
            return
        button.click()

    def _has_persistent_toolbar_mode(self) -> bool:
        return bool(preview_navigation_mode(self._toolbar))

    def _start_mode(self, watched, event, mode: str) -> bool:
        if self._toolbar is None or MouseButton is None:
            return False
        pos = self._event_pos(event)
        if self._axis_at(watched, pos) is None:
            return False
        if not self._has_persistent_toolbar_mode():
            self._temporary_mode = mode
            self._toggle_button_for_mode(mode, True)
        elif preview_navigation_mode(self._toolbar) != mode:
            return False
        mouse_button = MouseButton.RIGHT if mode == "pan" else MouseButton.LEFT
        mouse_event = self._build_mouse_event(watched, "button_press_event", pos, button=mouse_button, gui_event=event)
        if mouse_event is None:
            return False
        if mode == "pan":
            self._toolbar.press_pan(mouse_event)
        else:
            self._toolbar.press_zoom(mouse_event)
        self._active_mode = mode
        self._sync()
        return True

    def _drag_mode(self, watched, event) -> bool:
        if not self._active_mode:
            return False
        pos = self._event_pos(event)
        mouse_event = self._build_mouse_event(watched, "motion_notify_event", pos, gui_event=event)
        if mouse_event is None:
            return False
        if self._active_mode == "pan":
            self._toolbar.drag_pan(mouse_event)
        elif self._active_mode == "zoom":
            self._toolbar.drag_zoom(mouse_event)
        self._sync()
        return True

    def _finish_mode(self, watched, event) -> bool:
        if not self._active_mode or MouseButton is None:
            return False
        pos = self._event_pos(event)
        mouse_button = MouseButton.RIGHT if self._active_mode == "pan" else MouseButton.LEFT
        mouse_event = self._build_mouse_event(watched, "button_release_event", pos, button=mouse_button, gui_event=event)
        if mouse_event is None:
            return False
        if self._active_mode == "pan":
            self._toolbar.release_pan(mouse_event)
        elif self._active_mode == "zoom":
            self._toolbar.release_zoom(mouse_event)
        self._active_mode = ""
        temporary_mode = self._temporary_mode
        self._temporary_mode = ""
        if temporary_mode:
            self._toggle_button_for_mode(temporary_mode, False)
        self._sync()
        return True

    def eventFilter(self, watched, event) -> bool:
        if self._toolbar is None:
            return False
        if event.type() == QEvent.Type.Wheel:
            if self._axis_at(watched, self._event_pos(event)) is None:
                return False
            delta = event.angleDelta().y() if hasattr(event, "angleDelta") else 0
            if delta == 0:
                return False
            if self._buttons is not None:
                if delta > 0:
                    self._buttons.zoom_in.click()
                else:
                    self._buttons.zoom_out.click()
                self._sync()
                return True
            callback = self._zoom_in_callback if delta > 0 else self._zoom_out_callback
            if callable(callback):
                callback()
                self._sync()
                return True
            return False
        if event.type() == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.RightButton:
            return self._reset()
        if self._temporary_mode and event.type() in {QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease}:
            if event.type() == QEvent.Type.MouseMove:
                return self._drag_mode(watched, event)
            if self._temporary_mode == "zoom" and event.button() == Qt.MouseButton.LeftButton:
                return self._finish_mode(watched, event)
            if self._temporary_mode == "pan" and event.button() == Qt.MouseButton.RightButton:
                return self._finish_mode(watched, event)
            return False
        if self._has_persistent_toolbar_mode():
            return False
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.RightButton:
                return self._start_mode(watched, event, "pan")
            if event.button() == Qt.MouseButton.LeftButton:
                return self._start_mode(watched, event, "zoom")
            return False
        if event.type() == QEvent.Type.MouseMove:
            return self._drag_mode(watched, event)
        if event.type() == QEvent.Type.MouseButtonRelease:
            if self._active_mode == "zoom" and event.button() == Qt.MouseButton.LeftButton:
                return self._finish_mode(watched, event)
            if self._active_mode == "pan" and event.button() == Qt.MouseButton.RightButton:
                return self._finish_mode(watched, event)
        return False


def create_navigation_toolbar(
    canvas,
    parent: QWidget,
    *,
    sync_callback: Optional[Callable[[], None]] = None,
    reset_callback: Optional[Callable[[], None]] = None,
    zoom_in_callback: Optional[Callable[[], None]] = None,
    zoom_out_callback: Optional[Callable[[], None]] = None,
):
    if canvas is None or NavigationToolbar is None:
        return None
    toolbar = NavigationToolbar(canvas, parent)
    toolbar.hide()
    gesture_filter = _PreviewGestureFilter(
        toolbar,
        sync_callback,
        reset_callback=reset_callback,
        zoom_in_callback=zoom_in_callback,
        zoom_out_callback=zoom_out_callback,
        parent=canvas,
    )
    canvas.installEventFilter(gesture_filter)
    setattr(canvas, "_preview_gesture_filter", gesture_filter)
    return toolbar


def attach_preview_gesture_buttons(canvas, buttons: PreviewToolbarButtons) -> None:
    gesture_filter = getattr(canvas, "_preview_gesture_filter", None)
    if gesture_filter is not None and hasattr(gesture_filter, "set_buttons"):
        gesture_filter.set_buttons(buttons)


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
