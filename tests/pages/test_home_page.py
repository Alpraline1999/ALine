"""HomePage 引导入口与扩展状态 — 从 test_ui.py 提取。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from tests.ui_test_helpers import setUpModule, tearDownModule  # noqa: F401


class TestHomePage(unittest.TestCase):
    """HomePage 引导入口与扩展状态"""

    def test_home_page_builds_banner_with_two_reserved_link_cards(self):
        from ui.pages.home_page import HomePage, _HOME_CONTENT_MARGIN, _HOME_LINK_CARD_HEIGHT, _HOME_LINK_CARD_WIDTH

        page = HomePage()
        try:
            page.resize(1200, 900)
            page.show()
            QApplication.processEvents()
            self.assertIsNotNone(page._banner)
            self.assertEqual(page._banner.x(), 0)
            self.assertEqual(page._banner.y(), 0)
            self.assertEqual(page._banner.width(), page.width())
            self.assertFalse(page._banner._background.isNull())
            self.assertEqual(page._banner._hero_title.text(), "ALine")
            self.assertEqual(page._banner._hero_subtitle.text(), "科研数据管理与可视化工作台")
            self.assertEqual(page._banner._hero_hint.maximumWidth(), 760)
            self.assertGreaterEqual(page._banner._hero_hint.height(), page._banner._hero_hint.sizeHint().height())
            self.assertIsNotNone(page._banner._link_card_view)
            self.assertEqual(page._banner._link_card_view._layout.count(), 2)
            self.assertEqual([card.titleLabel.text() for card in page._banner._link_cards], ["软件主页", "GitHub 仓库"])
            self.assertEqual(page._banner._link_cards[0]._icon_source, page._banner._card_icon_path)
            self.assertEqual(page._banner._link_cards[0].width(), _HOME_LINK_CARD_WIDTH)
            self.assertEqual(page._banner._link_cards[0].height(), _HOME_LINK_CARD_HEIGHT)
            card_left = page._banner._link_cards[0].mapTo(page, page._banner._link_cards[0].rect().topLeft()).x()
            new_button_left = page._new_btn.mapTo(page, page._new_btn.rect().topLeft()).x()
            self.assertEqual(card_left, new_button_left)
            self.assertEqual(new_button_left, _HOME_CONTENT_MARGIN)
        finally:
            page.deleteLater()

    def test_home_page_action_buttons_are_left_aligned(self):
        from ui.pages.home_page import HomePage

        page = HomePage()
        try:
            self.assertEqual(page._action_button_layout.spacing(), 20)
            self.assertTrue(bool(page._action_button_layout.alignment() & Qt.AlignmentFlag.AlignLeft))
            self.assertEqual(page._new_btn.width(), 150)
            self.assertEqual(page._open_btn.width(), 150)
        finally:
            page.deleteLater()

    def test_home_page_hides_guide_button_without_extension_status_summary(self):
        from core.ui_preferences import set_home_onboarding_completed
        from ui.pages.home_page import HomePage

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "ui_preferences.json"
            with mock.patch("core.ui_preferences._CONFIG_PATH", config_path):
                set_home_onboarding_completed(True)
                page = HomePage()
                try:
                    self.assertIsNone(page._guide_toggle_btn)
                    self.assertIsNone(page._extension_status_btn)
                    self.assertIsNone(page._status_bar)
                finally:
                    page.deleteLater()

    def test_home_page_no_longer_uses_bottom_extension_status_bar(self):
        from ui.pages.home_page import HomePage

        page = HomePage()
        try:
            self.assertIsNone(page._status_bar)
            self.assertIsNone(page._extension_status_btn)
            self.assertEqual(len(page._home_onboarding_steps()), 4)
        finally:
            page.deleteLater()

    def test_home_page_recent_scroll_expands_to_fill_remaining_height(self):
        from PySide6.QtWidgets import QSizePolicy
        from ui.pages.home_page import HomePage

        with mock.patch(
            "ui.pages.home_page.load_recent",
            return_value=[{"name": "示例项目", "path": "/tmp/example.aline", "opened_at": "2026-04-23 10:20:30"}],
        ):
            page = HomePage()
        try:
            self.assertEqual(page._recent_scroll.sizePolicy().verticalPolicy(), QSizePolicy.Policy.Expanding)
            self.assertEqual(page._recent_scroll.maximumHeight(), 16777215)
            self.assertFalse(page._recent_scroll.isHidden())
            self.assertTrue(page._no_recent.isHidden())
            self.assertEqual(page._content_layout.stretch(page._content_layout.indexOf(page._recent_scroll)), 1)
        finally:
            page.deleteLater()

    def test_home_page_recent_section_uses_compact_layout_when_empty(self):
        from PySide6.QtWidgets import QSizePolicy
        from ui.pages.home_page import HomePage, _HOME_CONTENT_MARGIN

        with mock.patch("ui.pages.home_page.load_recent", return_value=[]):
            page = HomePage()
        try:
            page.resize(1200, 900)
            page.show()
            QApplication.processEvents()
            self.assertFalse(page._no_recent.isHidden())
            self.assertTrue(page._recent_scroll.isHidden())
            self.assertEqual(page._recent_scroll.sizePolicy().verticalPolicy(), QSizePolicy.Policy.Preferred)
            self.assertEqual(page._content_layout.stretch(page._content_layout.indexOf(page._recent_scroll)), 0)
            self.assertGreater(page._no_recent.width(), 1000)
            self.assertLess(page._no_recent.height(), 40)
            self.assertEqual(page._no_recent.x(), _HOME_CONTENT_MARGIN)
            self.assertLess(page._content_widget.height(), 260)
            self.assertLess(page._recent_label.height(), 30)
        finally:
            page.deleteLater()

    def test_home_page_recent_rows_use_shared_hover_color(self):
        from ui.pages.home_page import HomePage
        from ui.theme import hover_color

        with mock.patch(
            "ui.pages.home_page.load_recent",
            return_value=[{"name": "示例项目", "path": "/tmp/example.aline", "opened_at": "2026-04-23 10:20:30"}],
        ):
            page = HomePage()

        try:
            row = self._first_recent_row(page)
            self.assertIsNotNone(row)
            self.assertIn(hover_color(), row.styleSheet())
        finally:
            page.deleteLater()

    def test_home_page_recent_tooltips_use_fluent_filters(self):
        from PySide6.QtWidgets import QWidget
        from ui.pages.home_page import HomePage

        with mock.patch(
            "ui.pages.home_page.load_recent",
            return_value=[{"name": "示例项目", "path": "/tmp/example.aline", "opened_at": "2026-04-23 10:20:30"}],
        ):
            page = HomePage()

        try:
            tooltip_widgets = [
                widget
                for widget in page.findChildren(QWidget)
                if widget.toolTip() in {"/tmp/example.aline", "从列表移除"}
            ]
            self.assertEqual(len(tooltip_widgets), 2)
            for widget in tooltip_widgets:
                self.assertTrue(widget.property("_alineFluentTooltip"))
        finally:
            page.deleteLater()

    def test_home_page_infobar_uses_top_level_parent(self):
        from PySide6.QtWidgets import QWidget
        from ui.pages import home_page
        from ui.pages.home_page import HomePage

        host = QWidget()
        page = HomePage(parent=host)
        try:
            with mock.patch.object(type(home_page.project_manager), "current_project", new_callable=mock.PropertyMock, return_value=None):
                with mock.patch.object(home_page.InfoBar, "warning") as warning_mock:
                    page._request_quick_start("chart")

            warning_mock.assert_called_once()
            self.assertIs(warning_mock.call_args.kwargs["parent"], host)
        finally:
            page.deleteLater()
            host.deleteLater()

    @staticmethod
    def _first_recent_row(page):
        for index in range(page._recent_items_layout.count()):
            item = page._recent_items_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is not None:
                return widget
        return None
