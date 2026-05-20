from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from processing.async_runner import AsyncPipelineRunner

_app = None


def setUpModule():
    global _app
    if QApplication.instance() is None:
        _app = QApplication(sys.argv)
    else:
        _app = QApplication.instance()


def tearDownModule():
    global _app
    app = QApplication.instance()
    if app is not None:
        for widget in list(app.topLevelWidgets()):
            try:
                widget.close()
                widget.deleteLater()
            except RuntimeError:
                continue
        app.processEvents()
    _app = None


class TestAsyncPipelineRunner(unittest.TestCase):

    def test_runner_signals(self):
        runner = AsyncPipelineRunner()

        received = []
        runner.progress.connect(lambda p, d: received.append(("progress", p)))

        finished_received = []

        def on_finished(lines, warns):
            finished_received.append((lines, warns))
            loop.quit()

        runner.finished.connect(on_finished)

        error_occurred = []

        def on_error(msg):
            error_occurred.append(msg)
            loop.quit()

        runner.error.connect(on_error)

        loop = QEventLoop()

        runner.run(
            lines=[{"x": [1.0, 2.0, 3.0], "y": [4.0, 5.0, 6.0], "name": "test"}],
            ops=[{"type": "normalize", "params": {"mode": "minmax"}}],
        )

        QTimer.singleShot(30000, loop.quit)
        loop.exec()

        runner.cleanup()

        self.assertEqual(
            len(error_occurred), 0,
            f"Should not receive errors: {error_occurred}",
        )
        self.assertTrue(
            any(r[0] == "progress" for r in received),
            "Should receive progress signals",
        )
        self.assertEqual(
            len(finished_received), 1,
            "Should receive exactly one finished signal",
        )
        result_lines, _warnings = finished_received[0]
        self.assertEqual(len(result_lines), 1)
        self.assertIn("x", result_lines[0])
        self.assertIn("y", result_lines[0])

    def test_runner_empty_ops(self):
        runner = AsyncPipelineRunner()

        finished_received = []

        def on_finished(lines, warns):
            finished_received.append((lines, warns))
            loop.quit()

        runner.finished.connect(on_finished)

        error_occurred = []

        def on_error(msg):
            error_occurred.append(msg)
            loop.quit()

        runner.error.connect(on_error)

        loop = QEventLoop()

        input_lines = [{"x": [1.0, 2.0], "y": [3.0, 4.0], "name": "empty_test"}]
        runner.run(lines=input_lines, ops=[])

        QTimer.singleShot(30000, loop.quit)
        loop.exec()

        runner.cleanup()

        self.assertEqual(len(error_occurred), 0)
        self.assertEqual(len(finished_received), 1)
        result_lines, _warnings = finished_received[0]
        self.assertEqual(result_lines, input_lines)

    def test_runner_cancellation(self):
        runner = AsyncPipelineRunner()

        progress_received = []
        runner.progress.connect(lambda p, d: progress_received.append((p, d)))

        cancelled_received = []

        def on_cancelled():
            cancelled_received.append(True)
            loop.quit()

        runner.cancelled.connect(on_cancelled)

        finished_received = []
        runner.finished.connect(lambda *_: finished_received.append(True))

        loop = QEventLoop()

        runner.run(
            lines=[{"x": [1.0, 2.0, 3.0], "y": [4.0, 5.0, 6.0], "name": "t"}],
            ops=[
                {"type": "normalize", "params": {"mode": "minmax"}},
                {"type": "smooth", "params": {"method": "savgol", "window": 5, "poly": 2}},
                {"type": "crop", "params": {"x_min": 0.0, "x_max": 10.0}},
            ],
        )

        # Cancel before entering the event loop so the cancel signal
        # is queued ahead of any pipeline progress.
        runner.cancel()
        QTimer.singleShot(30000, loop.quit)
        loop.exec()

        runner.cleanup()

        self.assertEqual(len(cancelled_received), 1, "Should receive cancelled signal")
        self.assertEqual(len(finished_received), 0, "Should NOT receive finished signal")

    def test_runner_multi_op_progress(self):
        runner = AsyncPipelineRunner()

        progress_received = []
        runner.progress.connect(lambda p, d: progress_received.append((p, d)))

        finished_received = []

        def on_finished(lines, warns):
            finished_received.append((lines, warns))
            loop.quit()

        runner.finished.connect(on_finished)

        error_occurred = []

        def on_error(msg):
            error_occurred.append(msg)
            loop.quit()

        runner.error.connect(on_error)

        loop = QEventLoop()

        runner.run(
            lines=[{"x": [1.0, 2.0, 3.0], "y": [4.0, 5.0, 6.0], "name": "t"}],
            ops=[
                {"type": "normalize", "params": {"mode": "minmax"}},
                {"type": "smooth", "params": {"method": "savgol", "window": 5, "poly": 2}},
            ],
        )

        QTimer.singleShot(30000, loop.quit)
        loop.exec()

        runner.cleanup()

        self.assertEqual(len(error_occurred), 0)
        self.assertTrue(len(progress_received) >= 2, "Should have progress for each op plus completion")
        self.assertEqual(len(finished_received), 1)

    def test_runner_step_completed_signal(self):
        runner = AsyncPipelineRunner()

        steps_received = []
        runner.step_completed.connect(lambda i, op_type, result: steps_received.append((i, op_type)))

        finished_received = []

        def on_finished(lines, warns):
            finished_received.append((lines, warns))
            loop.quit()

        runner.finished.connect(on_finished)

        loop = QEventLoop()

        runner.run(
            lines=[{"x": [1.0, 2.0, 3.0], "y": [4.0, 5.0, 6.0], "name": "t"}],
            ops=[
                {"type": "normalize", "params": {"mode": "minmax"}},
                {"type": "smooth", "params": {"method": "savgol", "window": 3, "poly": 1}},
            ],
        )

        QTimer.singleShot(30000, loop.quit)
        loop.exec()

        runner.cleanup()

        self.assertEqual(len(finished_received), 1)
        self.assertEqual(len(steps_received), 2)
        self.assertEqual(steps_received[0][1], "normalize")
        self.assertEqual(steps_received[1][1], "smooth")
