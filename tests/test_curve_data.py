from __future__ import annotations

import unittest

import numpy as np

from core.curve_data import CurveBuffer, SeriesArrayView
from core.line_tools import line_from_xy, line_xy


class TestCurveData(unittest.TestCase):
    def test_line_xy_returns_array_views(self) -> None:
        xs, ys = line_xy(line_from_xy([1, 2], [3, 4]))

        self.assertIsInstance(xs, SeriesArrayView)
        self.assertIsInstance(ys, SeriesArrayView)
        self.assertEqual(xs, [1.0, 2.0])
        self.assertEqual(ys, [3.0, 4.0])
        self.assertEqual(np.asarray(xs).tolist(), [1.0, 2.0])
        self.assertEqual(np.asarray(ys).tolist(), [3.0, 4.0])
        self.assertEqual(list(xs[:1]), [1.0])

    def test_curve_buffer_roundtrip(self) -> None:
        buffer = CurveBuffer.from_xy([0, 1, 2], [3, 4, 5])
        xs, ys = buffer.to_views()

        self.assertEqual(buffer.to_line(), [[0.0, 3.0], [1.0, 4.0], [2.0, 5.0]])
        self.assertEqual(xs, [0.0, 1.0, 2.0])
        self.assertEqual(ys, [3.0, 4.0, 5.0])
        self.assertTrue(xs)
        self.assertTrue(ys)
        self.assertEqual(buffer.to_series_payload(), {"x": [0.0, 1.0, 2.0], "y": [3.0, 4.0, 5.0]})


if __name__ == "__main__":
    unittest.main()
