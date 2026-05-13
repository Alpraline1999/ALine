from __future__ import annotations

import time
import unittest

from core.extension_sandbox import SandboxedExtensionRunner
from core.line_tools import line_from_xy, line_xy


def _identity_handler(lines, params):
    return lines[0]


def _double_y_handler(lines, params):
    xs, ys = line_xy(lines[0])
    return line_from_xy(xs, [y * params.get("factor", 1) for y in ys])


def _crashing_handler(lines, params):
    return 1 / 0


def _timeout_handler(lines, params):
    time.sleep(10)
    return lines[0]


def _squaring_handler(lines, params):
    xs, ys = line_xy(lines[0])
    return line_from_xy(
        [x + params.get("offset", 0) for x in xs],
        [y * y for y in ys],
    )


class TestSandboxedExtensionRunner(unittest.TestCase):

    def setUp(self):
        self.sample_line = line_from_xy([1.0, 2.0, 3.0], [4.0, 5.0, 6.0])

    def test_sandbox_execution_succeeds(self):
        result = SandboxedExtensionRunner.run(_identity_handler, [self.sample_line], {})
        self.assertTrue(result["success"])
        self.assertEqual(line_xy(result["result"]), ([1.0, 2.0, 3.0], [4.0, 5.0, 6.0]))

    def test_sandbox_execution_with_params(self):
        result = SandboxedExtensionRunner.run(
            _double_y_handler, [self.sample_line], {"factor": 3}
        )
        self.assertTrue(result["success"])
        self.assertEqual(line_xy(result["result"]), ([1.0, 2.0, 3.0], [12.0, 15.0, 18.0]))

    def test_crash_isolated_from_main_process(self):
        result = SandboxedExtensionRunner.run(_crashing_handler, [self.sample_line], {})
        self.assertFalse(result["success"])
        self.assertIn("ZeroDivisionError", result.get("error", ""))
        self.assertIn("traceback", result)
        self.assertIn("ZeroDivisionError", result.get("traceback", ""))

    def test_timeout_termination(self):
        result = SandboxedExtensionRunner.run(
            _timeout_handler, [self.sample_line], {}, timeout=1
        )
        self.assertFalse(result["success"])
        self.assertIn("超时", result.get("error", ""))

    def test_sandbox_preserves_line_structure(self):
        xs = [0.0, 0.5, 1.0]
        ys = [0.0, 0.25, 1.0]
        line = line_from_xy(xs, ys)

        result = SandboxedExtensionRunner.run(_squaring_handler, [line], {"offset": 0.1})
        self.assertTrue(result["success"])
        out_xs, out_ys = line_xy(result["result"])
        self.assertEqual(out_xs, [0.1, 0.6, 1.1])
        self.assertEqual(out_ys, [0.0, 0.0625, 1.0])

    def test_sandbox_with_empty_params(self):
        result = SandboxedExtensionRunner.run(_identity_handler, [self.sample_line], {})
        self.assertTrue(result["success"])
        self.assertEqual(line_xy(result["result"]), ([1.0, 2.0, 3.0], [4.0, 5.0, 6.0]))


if __name__ == "__main__":
    unittest.main()
