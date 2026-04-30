from __future__ import annotations

import unittest

from ui.pages.digitize_page import _build_digitize_auto_preview_points


class TestDigitizeAutoDetect(unittest.TestCase):
    def test_build_digitize_auto_preview_points(self) -> None:
        calls: list[tuple[object, str, dict[str, object]]] = []

        def invoke_handler(handler, image_path: str, params: dict[str, object]):
            calls.append((handler, image_path, params))
            return [(1, 2), (3, 4)]

        def line_xy_fn(result):
            self.assertEqual(result, [(1, 2), (3, 4)])
            return [0.5, 1.5], [2.5, 3.5]

        points = _build_digitize_auto_preview_points(
            invoke_handler,
            line_xy_fn,
            handler="fake-handler",
            image_path="/tmp/image.png",
            params={"threshold": 42},
        )

        self.assertEqual(calls, [("fake-handler", "/tmp/image.png", {"threshold": 42})])
        self.assertEqual(points, [(0.5, 2.5), (1.5, 3.5)])
