from __future__ import annotations

import unittest

from core.extension_api import normalize_extension_lines_list
from processing.data_engine import _op_lines_list, apply_operation_to_lines


class TestExtensionProtocolCleanup(unittest.TestCase):
    def test_lines_list_sentinals_are_rejected(self) -> None:
        for raw in ("all", ":", "*", "selected"):
            with self.assertRaises(ValueError):
                normalize_extension_lines_list(raw)

    def test_nested_lines_protocol_is_rejected_by_pipeline_helper(self) -> None:
        op = {"params": {"lines": {"lines_list": [1, 2]}}}
        indices, present = _op_lines_list(op)
        self.assertEqual(indices, [])
        self.assertFalse(present)

    def test_pipeline_line_payload_bool_fields_are_normalized(self) -> None:
        lines, warnings = apply_operation_to_lines(
            [{"name": "bad", "x": True, "y": True}],
            {"type": "crop", "params": {"x_min": 0.0, "x_max": 1.0}},
        )

        self.assertEqual(warnings, [])
        self.assertEqual(lines[0]["x"], [])
        self.assertEqual(lines[0]["y"], [])


if __name__ == "__main__":
    unittest.main()
