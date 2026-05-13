from __future__ import annotations

import traceback
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, QThread, Signal


class AsyncPipelineRunner(QObject):

    progress = Signal(int, str)
    step_completed = Signal(int, str, object)
    finished = Signal(list, list)
    error = Signal(str)
    cancelled = Signal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._thread: Optional[QThread] = None
        self._worker: Optional[_PipelineWorker] = None

    def run(
        self,
        lines: List[Dict[str, Any]],
        ops: List[Dict[str, Any]],
        selected_lines: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self._thread = QThread(self)
        self._worker = _PipelineWorker(lines, ops, selected_lines)
        self._worker.moveToThread(self._thread)

        self._worker.progress.connect(self.progress)
        self._worker.step_completed.connect(self.step_completed)
        self._worker.finished.connect(self.finished)
        self._worker.error.connect(self.error)
        self._worker.cancelled.connect(self.cancelled)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def cancel(self) -> None:
        if self._worker is not None:
            self._worker._cancelled = True

    def wait(self, timeout_ms: int = 30000) -> bool:
        if self._thread is not None:
            return self._thread.wait(timeout_ms)
        return True

    def cleanup(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(5000)
            self._thread.deleteLater()
            self._thread = None
        self._worker = None


class _PipelineWorker(QObject):

    progress = Signal(int, str)
    step_completed = Signal(int, str, object)
    finished = Signal(list, list)
    error = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        lines: List[Dict[str, Any]],
        ops: List[Dict[str, Any]],
        selected_lines: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        super().__init__()
        self._lines = lines
        self._ops = ops
        self._selected_lines = selected_lines
        self._cancelled = False

    def run(self) -> None:
        try:
            from processing.data_engine import apply_pipeline_to_lines

            total = len(self._ops)
            if total == 0:
                self.progress.emit(100, "完成")
                self.finished.emit(self._lines, [])
                return

            result = self._lines
            warnings: List[str] = []

            for i, op in enumerate(self._ops):
                if self._cancelled:
                    self.cancelled.emit()
                    return

                op_type = str(op.get("type", "unknown") or "unknown")
                self.progress.emit(int((i / total) * 100), f"正在执行: {op_type}")

                result, step_warnings = apply_pipeline_to_lines(
                    result,
                    [op],
                    selected_lines=self._selected_lines,
                )
                warnings.extend(step_warnings)

                self.step_completed.emit(i, op_type, result)

            self.progress.emit(100, "完成")
            self.finished.emit(result, warnings)

        except Exception as e:
            self.error.emit(
                f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            )
