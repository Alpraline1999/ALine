from __future__ import annotations

import unittest

from ui import dialogs, widgets
from ui.pages import analysis_page_support, chart_page_support, data_page_support, digitize_page_support
from ui.pages import process_page
from ui.widgets import project_tree_support


class TestPageSupportModules(unittest.TestCase):
    def test_project_tree_support_exports_basic_constants(self) -> None:
        self.assertIn("datasets", project_tree_support._ROOT_GROUP_ORDER)
        self.assertIn("data_file", project_tree_support._KIND_CONFIG)

    def test_data_page_support_exports_base_symbols(self) -> None:
        self.assertTrue(data_page_support.HAS_MATPLOTLIB is False or data_page_support.HAS_MATPLOTLIB is True)
        self.assertIn(".png", data_page_support._SOURCE_IMAGE_SUFFIXES)

    def test_process_page_support_exports_matplotlib_flag(self) -> None:
        self.assertTrue(process_page.HAS_MATPLOTLIB is False or process_page.HAS_MATPLOTLIB is True)

    def test_chart_page_support_exports_base_symbols(self) -> None:
        self.assertEqual("默认", chart_page_support._THEME_HINTS["默认"] and "默认")
        self.assertEqual("base_curve_style_controls", chart_page_support._BASE_CURVE_STYLE_EXTENSION_TYPE)

    def test_digitize_page_support_exports_input_dialog(self) -> None:
        self.assertTrue(hasattr(digitize_page_support, "_InputDialog"))
        self.assertIn(".webp", digitize_page_support._SUPPORTED_SOURCE_IMAGE_SUFFIXES)

    def test_analysis_page_support_exports_result_helpers(self) -> None:
        self.assertTrue(hasattr(analysis_page_support, "_SelectableResultTable"))
        self.assertIn("curve_fit", analysis_page_support._PREFERRED_ANALYSIS_ORDER)

    def test_dialogs_and_widgets_package_exports_are_explicit(self) -> None:
        self.assertIn("CalibrationDialog", dialogs.__all__)
        self.assertIn("SelectionDialog", dialogs.__all__)
        self.assertIn("ImageViewer", widgets.__all__)
        self.assertIn("ProjectTreeWidget", widgets.__all__)
