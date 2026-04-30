from __future__ import annotations

import unittest

from core.report_templates import DEFAULT_REPORT_TEMPLATE


class TestReportTemplates(unittest.TestCase):
    def test_default_report_template_contains_expected_sections(self) -> None:
        self.assertIn("# 数据分析报告", DEFAULT_REPORT_TEMPLATE)
        self.assertIn("{{table:analysis_results}}", DEFAULT_REPORT_TEMPLATE)


if __name__ == "__main__":
    unittest.main()
