"""
跨页面共享的后台任务壳层。

提供 BackgroundTask QObject，通过信号报告进度/结果，
支持取消和过期结果保护。
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QTimer, Signal


class BackgroundTask(QObject):
    """可在后台线程执行的 Qt 任务壳层。

    Signals:
        progress_changed(task_id, text, percent)
        finished(task_id, result)
        error_occurred(task_id, error_msg)
    """
    progress_changed = Signal(str, str, float)
    finished = Signal(str, object)
    error_occurred = Signal(str, str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._task_id: str = ""
        self._cancelled = False
        self._thread: Optional[threading.Thread] = None

    def run(
        self,
        task_id: str,
        target: Callable[..., Any],
        args: tuple[Any, ...] = (),
        kwargs: Optional[dict[str, Any]] = None,
    ) -> None:
        """启动后台任务。

        Args:
            task_id: 任务标识，用于过期结果保护
            target: 可调用对象
            args: 位置参数
            kwargs: 关键字参数
        """
        self._task_id = task_id
        self._cancelled = False
        kwargs = kwargs or {}
        self._thread = threading.Thread(
            target=self._run_wrapper,
            args=(target, args, kwargs),
            daemon=True,
        )
        self._thread.start()

    def cancel(self) -> None:
        """取消当前任务（标记取消，不强制终止线程）。"""
        self._cancelled = True

    @property
    def task_id(self) -> str:
        return self._task_id

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def report_progress(self, text: str = "", percent: float = 0.0) -> None:
        """在后台线程中调用以报告进度。"""
        self.progress_changed.emit(self._task_id, text, percent)

    def _run_wrapper(self, target: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        try:
            result = target(*args, **kwargs)
            if not self._cancelled:
                self.finished.emit(self._task_id, result)
        except Exception as exc:
            if not self._cancelled:
                self.error_occurred.emit(self._task_id, str(exc))


class TaskManager(QObject):
    """管理多个 BackgroundTask 的生命周期和过期保护。"""

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._tasks: dict[str, BackgroundTask] = {}
        self._current_job_ids: dict[str, str] = {}  # task_type -> latest job_id

    def run(
        self,
        task_type: str,
        job_id: str,
        target: Callable[..., Any],
        args: tuple[Any, ...] = (),
        kwargs: Optional[dict[str, Any]] = None,
        *,
        on_finished: Optional[Callable[[str, Any], None]] = None,
        on_error: Optional[Callable[[str, str], None]] = None,
    ) -> BackgroundTask:
        """启动任务，自动取消同一 type 的旧任务。

        Args:
            task_type: 任务类型（如 "process_pipeline"）
            job_id: 当前 job 标识
            target: 可调用对象
        """
        # 取消旧任务
        old_id = self._current_job_ids.get(task_type)
        if old_id and old_id in self._tasks:
            self._tasks[old_id].cancel()

        self._current_job_ids[task_type] = job_id
        task = BackgroundTask(self)
        task.finished.connect(self._on_task_finished)
        task.error_occurred.connect(self._on_task_error)
        if on_finished is not None:
            task.finished.connect(on_finished)
        if on_error is not None:
            task.error_occurred.connect(on_error)
        self._tasks[job_id] = task
        task.run(job_id, target, args, kwargs)
        # 用 QTimer 做清理保护
        QTimer.singleShot(60000, lambda: self._cleanup_old_task(job_id))
        return task

    def get_task(self, task_type: str) -> Optional[BackgroundTask]:
        """获取当前最新任务（如果有）。"""
        job_id = self._current_job_ids.get(task_type)
        if job_id and job_id in self._tasks:
            return self._tasks[job_id]
        return None

    def get_progress(self, task_type: str) -> tuple[str, str, float]:
        """获取当前进度。返回 (status, text, percent)。"""
        task = self.get_task(task_type)
        if task is None:
            return ("idle", "", 0.0)
        if task.is_cancelled:
            return ("cancelled", "", 0.0)
        if task.is_running:
            return ("running", "", 0.0)
        return ("completed", "", 100.0)

    def cancel_all(self) -> None:
        """取消所有运行中的任务。"""
        for task in self._tasks.values():
            task.cancel()

    def _on_task_finished(self, task_id: str, result: Any) -> None:
        if self._is_stale(task_id):
            return
        if task_id in self._tasks:
            del self._tasks[task_id]

    def _on_task_error(self, task_id: str, error: str) -> None:
        if self._is_stale(task_id):
            return
        if task_id in self._tasks:
            del self._tasks[task_id]

    def _is_stale(self, task_id: str) -> bool:
        """检查任务结果是否已过期。"""
        for task_type, latest_id in self._current_job_ids.items():
            if latest_id == task_id:
                return False
        return True

    def _cleanup_old_task(self, job_id: str) -> None:
        if job_id in self._tasks:
            del self._tasks[job_id]
