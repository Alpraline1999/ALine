from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget
from qfluentwidgets import FluentIcon as FIF, ToggleToolButton

from ui.widgets.matplotlib_preview import PreviewToolbarButtons, _PreviewGestureFilter


_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication(sys.argv)


def tearDownModule() -> None:
    global _app
    app = QApplication.instance()
    if app is not None:
        for widget in list(app.topLevelWidgets()):
            try:
                widget.close()
                widget.deleteLater()
            except RuntimeError:
                continue
        app.processEvents()
    _app = None


class TestMatplotlibPreviewRuntime(unittest.TestCase):
    def test_mouse_mode_does_not_toggle_toolbar_buttons(self) -> None:
        parent = QWidget()
        toolbar = mock.Mock()
        toolbar.mode = ""
        event = mock.Mock()
        event.pos.return_value = mock.Mock(x=lambda: 10, y=lambda: 10)
        event.button.return_value = 1

        buttons = PreviewToolbarButtons(
            fit=mock.Mock(),
            zoom_in=mock.Mock(),
            zoom_out=mock.Mock(),
            pan=ToggleToolButton(FIF.MOVE, parent),
            box_zoom=ToggleToolButton(FIF.ZOOM, parent),
        )
        gesture_filter = _PreviewGestureFilter(toolbar, sync_callback=lambda: None, parent=parent)
        gesture_filter.set_buttons(buttons)

        with mock.patch.object(gesture_filter, "_axis_at", return_value=object()), \
             mock.patch.object(gesture_filter, "_build_mouse_event", return_value=object()):
            handled = gesture_filter._start_mode(object(), event, "pan")
            self.assertTrue(handled)
            self.assertFalse(buttons.pan.isChecked())
            self.assertFalse(buttons.box_zoom.isChecked())
            self.assertEqual(toolbar.press_pan.call_count, 1)

            buttons.pan.setChecked(True)
            buttons.box_zoom.setChecked(False)
            gesture_filter._active_mode = "pan"
            handled = gesture_filter._finish_mode(object(), event)
            self.assertTrue(handled)
            self.assertTrue(buttons.pan.isChecked())
            self.assertFalse(buttons.box_zoom.isChecked())
            self.assertEqual(toolbar.release_pan.call_count, 1)


if __name__ == "__main__":
    unittest.main()
