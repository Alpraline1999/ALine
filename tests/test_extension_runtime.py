from __future__ import annotations

import unittest

from core.extension_runtime import DEFAULT_EXTENSION_RUNTIME, ExtensionExecutionRequest
from core.line_tools import line_from_xy, line_xy


class TestExtensionRuntime(unittest.TestCase):
    def test_request_builds_curve_buffers(self) -> None:
        request = ExtensionExecutionRequest.from_series_payloads(
            "processing",
            "demo",
            [{"x": [1, 2], "y": [3, 4]}],
            {"offset": 1},
        )

        self.assertEqual(request.category, "processing")
        self.assertEqual(request.type_id, "demo")
        self.assertEqual(len(request.inputs), 1)
        self.assertEqual(request.inputs[0].to_line(), [[1.0, 3.0], [2.0, 4.0]])
        self.assertEqual(request.params, {"offset": 1})

    def test_runtime_can_invoke_processing_handler(self) -> None:
        def handler(lines, params):
            xs, ys = line_xy(lines[0])
            return line_from_xy(xs, [value + params["offset"] for value in ys])

        result = DEFAULT_EXTENSION_RUNTIME.invoke_processing(
            handler,
            [{"x": [0, 1], "y": [2, 3]}],
            {"offset": 2},
        )

        self.assertEqual(line_xy(result), ([0.0, 1.0], [4.0, 5.0]))


if __name__ == "__main__":
    unittest.main()
