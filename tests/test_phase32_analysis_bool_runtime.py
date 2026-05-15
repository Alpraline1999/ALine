from __future__ import annotations

import unittest
from types import SimpleNamespace

from ui.pages.analysis_page import AnalysisPage


class TestPhase32AnalysisBoolRuntime(unittest.TestCase):
    @staticmethod
    def _make_page() -> AnalysisPage:
        page = AnalysisPage.__new__(AnalysisPage)
        page._analysis_label_map = {}
        page._result = {}
        return page

    def test_saved_result_input_refs_bool_is_treated_as_empty(self) -> None:
        page = self._make_page()
        analysis = SimpleNamespace(params={"input_refs": True}, input_series_ids=[])

        self.assertEqual(page._analysis_inputs_payloads(analysis), [])

    def test_report_render_context_handles_bool_payload_fields(self) -> None:
        page = self._make_page()

        context = page._build_report_render_context([
            {
                "title": "峰谷检测结果",
                "result": {
                    "analysis_type": "peak_detect",
                    "params": True,
                    "param_names": False,
                    "peaks": True,
                    "valleys": False,
                },
            }
        ])

        self.assertEqual(context["result_count"], "1")
        self.assertIn("峰谷检测结果", context["multi_result_sections"])
        self.assertIn("峰值=0，波谷=0", context["_analysis_results_table"])


if __name__ == "__main__":
    unittest.main()
