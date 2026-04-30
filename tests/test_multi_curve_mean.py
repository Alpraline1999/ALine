from __future__ import annotations

import unittest
from unittest import mock

from extensions.processing import multi_curve_mean as multi_curve_mean_module


class TestMultiCurveMean(unittest.TestCase):
    def test_multi_curve_mean_returns_pointwise_average(self) -> None:
        result = multi_curve_mean_module.multi_curve_mean_handler(
            [
                [[0.0, 1.0], [1.0, 3.0], [2.0, 5.0]],
                [[0.0, 3.0], [1.0, 5.0], [2.0, 7.0]],
            ],
            {},
        )

        self.assertEqual([[0.0, 2.0], [1.0, 4.0], [2.0, 6.0]], result)

    def test_multi_curve_mean_does_not_recompute_views_per_point(self) -> None:
        lines = [
            [[float(index), float(index + offset)] for index in range(32)]
            for offset in (0.0, 2.0, 4.0)
        ]
        real_line_xy = multi_curve_mean_module.line_xy
        call_count = 0

        def _counting_line_xy(line):
            nonlocal call_count
            call_count += 1
            return real_line_xy(line)

        with mock.patch.object(multi_curve_mean_module, "line_xy", side_effect=_counting_line_xy):
            result = multi_curve_mean_module.multi_curve_mean_handler(lines, {})

        self.assertEqual(32, len(result))
        self.assertLessEqual(call_count, len(lines) + 1)


if __name__ == "__main__":
    unittest.main()
