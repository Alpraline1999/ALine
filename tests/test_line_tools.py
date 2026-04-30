from __future__ import annotations

import unittest

from core.curve_data import CurveBuffer
from core.line_tools import line_from_xy, line_xy, series_payloads_to_lines


class TestLineTools(unittest.TestCase):
    def test_line_from_xy_round_trip(self) -> None:
        line = line_from_xy([1, 2], [3, 4])

        self.assertEqual([[1.0, 3.0], [2.0, 4.0]], line)
        self.assertEqual(([1.0, 2.0], [3.0, 4.0]), line_xy(line))

    def test_series_payloads_to_lines(self) -> None:
        lines = series_payloads_to_lines([{"x": [1, 2], "y": [3, 4]}])

        self.assertEqual([[[1.0, 3.0], [2.0, 4.0]]], lines)

    def test_series_payloads_to_lines_accepts_curve_buffer(self) -> None:
        lines = series_payloads_to_lines([CurveBuffer.from_xy([1, 2], [3, 4])])

        self.assertEqual([[[1.0, 3.0], [2.0, 4.0]]], lines)


if __name__ == "__main__":
    unittest.main()
