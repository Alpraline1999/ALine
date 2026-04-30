from __future__ import annotations

import unittest

from tests.perf_samples import build_large_curve_points, build_large_workspace_payload


class TestPhase22Samples(unittest.TestCase):
    def test_large_curve_sample_shape(self) -> None:
        xs, ys = build_large_curve_points(10)
        self.assertEqual(10, len(xs))
        self.assertEqual(10, len(ys))
        self.assertGreater(xs[-1], xs[0])

    def test_large_workspace_sample_shape(self) -> None:
        payload = build_large_workspace_payload(curve_count=3, points_per_curve=20)
        self.assertEqual(3, payload["curve_count"])
        self.assertEqual(20, payload["points_per_curve"])
        self.assertEqual(3, len(payload["series"]))
