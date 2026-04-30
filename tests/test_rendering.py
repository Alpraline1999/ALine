from __future__ import annotations

import unittest

from core.rendering import RenderDecimationPolicy, build_render_decimation_indices, decimate_xy_for_rendering


class TestRendering(unittest.TestCase):
    def test_build_render_decimation_indices_keeps_small_series_intact(self) -> None:
        indices = build_render_decimation_indices(5, RenderDecimationPolicy(max_points=10))

        self.assertEqual([0, 1, 2, 3, 4], indices)

    def test_build_render_decimation_indices_preserves_endpoints(self) -> None:
        indices = build_render_decimation_indices(10, RenderDecimationPolicy(max_points=4))

        self.assertEqual(0, indices[0])
        self.assertEqual(9, indices[-1])
        self.assertLessEqual(len(indices), 5)

    def test_decimate_xy_for_rendering_aligns_values(self) -> None:
        xs = list(range(10))
        ys = [value * 10 for value in xs]

        render_xs, render_ys, indices = decimate_xy_for_rendering(xs, ys, RenderDecimationPolicy(max_points=4))

        self.assertEqual([xs[index] for index in indices], render_xs)
        self.assertEqual([ys[index] for index in indices], render_ys)
        self.assertEqual(xs[0], render_xs[0])
        self.assertEqual(xs[-1], render_xs[-1])


if __name__ == "__main__":
    unittest.main()
