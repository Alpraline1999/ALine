from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QSplitter, QWidget

from ui.pages.page_shell_helpers import ExtensionPanelShellMixin, apply_splitter_panel_visibility, sync_vertical_splitter_sizes


_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    if QApplication.instance() is None:
        _app = QApplication(sys.argv)
    else:
        _app = QApplication.instance()


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


class TestPageShellHelpers(unittest.TestCase):
    def test_sync_vertical_splitter_sizes_respects_user_resize_flag(self) -> None:
        splitter = QSplitter(Qt.Orientation.Vertical)
        top = QWidget(splitter)
        bottom = QWidget(splitter)
        splitter.addWidget(top)
        splitter.addWidget(bottom)
        splitter.resize(200, 300)
        splitter.setSizes([120, 180])
        before = splitter.sizes()

        sync_vertical_splitter_sizes(splitter, user_resized=True, upper_ratio=0.4)

        self.assertEqual(splitter.sizes(), before)

    def test_apply_splitter_panel_visibility_updates_sizes(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget(splitter)
        right = QWidget(splitter)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.resize(400, 200)
        splitter.show()
        app = QApplication.instance()
        assert app is not None
        app.processEvents()

        apply_splitter_panel_visibility(
            splitter,
            right,
            False,
            visible_sizes=(300, 100),
            hidden_sizes=(400, 0),
        )
        app.processEvents()
        hidden_sizes = splitter.sizes()
        hidden_visible = right.isVisible()

        apply_splitter_panel_visibility(
            splitter,
            right,
            True,
            visible_sizes=(280, 120),
            hidden_sizes=(400, 0),
        )
        app.processEvents()
        visible_sizes = splitter.sizes()
        visible_visible = right.isVisible()

        self.assertFalse(hidden_visible)
        self.assertTrue(visible_visible)
        self.assertEqual(hidden_sizes[-1], 0)
        self.assertGreater(visible_sizes[-1], 0)

    def test_extension_panel_shell_mixin_routes_visibility(self) -> None:
        class _DummyViewState:
            extension_panel_visible = False
            extension_panel_width = 96

        class _DummyShell(ExtensionPanelShellMixin):
            def __init__(self) -> None:
                self._view_state = _DummyViewState()
                self._splitter = QSplitter(Qt.Orientation.Horizontal)
                self._extension_panel = QWidget()
                self._splitter.addWidget(QWidget())
                self._splitter.addWidget(self._extension_panel)
                self._splitter.resize(240, 120)
                self._splitter.show()

            def _extension_panel_splitter(self):
                return self._splitter

            def _extension_panel_visible_sizes(self):
                return (120, self._view_state.extension_panel_width)

            def _extension_panel_hidden_sizes(self):
                return (240, 0)

        shell = _DummyShell()
        app = QApplication.instance()
        assert app is not None
        app.processEvents()

        self.assertTrue(shell.supports_extension_panel_toggle())
        self.assertFalse(shell.is_extension_panel_visible())

        shell.set_extension_panel_visible(True)
        app.processEvents()

        self.assertTrue(shell.is_extension_panel_visible())
        self.assertTrue(shell._extension_panel.isVisible())
