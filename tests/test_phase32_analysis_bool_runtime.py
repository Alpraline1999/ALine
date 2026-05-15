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

    def test_on_analysis_finished_sanitizes_bool_payload_before_show_result(self) -> None:
        page = self._make_page()
        page._task_manager = SimpleNamespace(_current_job_ids={"analysis": "job-1"})
        page._run_analysis_btn = SimpleNamespace(setEnabled=lambda _value: None)
        page._cancel_analysis_btn = SimpleNamespace(hide=lambda: None)
        page._set_analysis_status = lambda _text: None
        captured = {}
        page._show_result = lambda analysis_type, selected: captured.update(
            analysis_type=analysis_type,
            selected=list(selected),
            result=dict(page._result or {}),
        )

        page._on_analysis_finished(
            "analysis",
            {
                "analysis_type": "bool_payload",
                "lines": True,
                "_plot_series": True,
                "summary_items": True,
            },
            "bool_payload",
            [("x", "y", "series-a")],
            "job-1",
        )

        self.assertEqual(captured["analysis_type"], "bool_payload")
        self.assertEqual(captured["result"]["lines"], [])
        self.assertEqual(captured["result"]["_plot_series"], [])
        self.assertEqual(captured["result"]["summary_items"], [])


if __name__ == "__main__":
    unittest.main()
