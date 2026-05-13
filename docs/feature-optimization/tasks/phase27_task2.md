# Phase 27 Task 2: Pipeline 执行异步化

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`，阶段 `Phase 27`

## 目标

将 `ProcessingEngine.apply_pipeline_to_lines()` 从同步阻塞改为后台线程执行，使处理页和分析页在大输入时 UI 不冻结，并显示进度反馈。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `processing/async_runner.py` | **新建** |
| `ui/pages/process_page.py` | 集成异步执行 |
| `ui/pages/analysis_page.py` | 集成异步执行 |

## AsyncPipelineRunner 设计

```python
# processing/async_runner.py
from __future__ import annotations
import traceback
from typing import Any, Dict, List, Optional, Callable

from PySide6.QtCore import QObject, Signal, QThread


class AsyncPipelineRunner(QObject):
    """后台线程执行 Pipeline 操作。"""
    
    # 信号
    progress = Signal(int, str)  # 百分比(0-100), 当前操作描述
    step_completed = Signal(int, str, object)  # step_index, op_type, intermediate_result
    finished = Signal(list, list)  # result_lines, warnings
    error = Signal(str)           # 错误描述
    cancelled = Signal()          # 被取消
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: Optional[QThread] = None
        self._cancel_flag = False
    
    def run(self, lines: List[Dict], ops: List[Dict],
            selected_lines: Optional[List[Dict]] = None) -> None:
        """在后台线程执行 Pipeline。"""
        self._cancel_flag = False
        self._thread = QThread(self)
        worker = _PipelineWorker(lines, ops, selected_lines)
        worker.moveToThread(self._thread)
        
        # 连接信号
        worker.progress.connect(self.progress)
        worker.step_completed.connect(self.step_completed)
        worker.finished.connect(self.finished)
        worker.error.connect(self.error)
        
        self._thread.started.connect(worker.run)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()
    
    def cancel(self) -> None:
        """请求取消当前执行。"""
        self._cancel_flag = True
        # 检查完成后自动取消


class _PipelineWorker(QObject):
    """后台工作线程，不持有 UI 引用。"""
    
    progress = Signal(int, str)
    step_completed = Signal(int, str, object)
    finished = Signal(list, list)
    error = Signal(str)
    
    def __init__(self, lines, ops, selected_lines=None):
        super().__init__()
        self._lines = lines
        self._ops = ops
        self._selected_lines = selected_lines
    
    def run(self):
        try:
            from processing.data_engine import apply_pipeline_to_lines
            
            total = len(self._ops)
            result = self._lines
            warnings = []
            
            for i, op in enumerate(self._ops):
                # 检查取消
                # 注：需要在 apply_pipeline_to_lines 中注入取消检查点
                
                op_type = op.get("type", "unknown")
                self.progress.emit(int((i / total) * 100), f"正在执行: {op_type}")
                
                result, step_warnings = apply_pipeline_to_lines(
                    result, [op],
                    selected_lines=self._selected_lines,
                )
                warnings.extend(step_warnings)
                
                self.step_completed.emit(i, op_type, result)
            
            self.progress.emit(100, "完成")
            self.finished.emit(result, warnings)
            
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
```

## 在 ProcessPage 中集成

```python
# ui/pages/process_page.py
class ProcessPage:
    def __init__(self):
        self._runner: Optional[AsyncPipelineRunner] = None
    
    def _execute_pipeline(self):
        self._runner = AsyncPipelineRunner(self)
        self._runner.progress.connect(self._on_progress)
        self._runner.finished.connect(self._on_run_finished)
        self._runner.error.connect(self._on_run_error)
        self._runner.run(lines, ops)
        
        # UI 反馈：禁用执行按钮，显示进度条
        self._exec_btn.setEnabled(False)
        self._progress_bar.setVisible(True)
    
    def _on_progress(self, pct: int, desc: str):
        self._progress_bar.setValue(pct)
        self._status_label.setText(desc)
    
    def _on_run_finished(self, result, warnings):
        self._exec_btn.setEnabled(True)
        self._progress_bar.setVisible(False)
        # 更新预览
```

## 单元测试

```python
class TestAsyncPipelineRunner(unittest.TestCase):
    def test_runner_signals(self):
        runner = AsyncPipelineRunner()
        received = []
        runner.progress.connect(lambda p, d: received.append(("progress", p)))
        
        runner.run(
            lines=[{"x": [1, 2, 3], "y": [4, 5, 6], "name": "t"}],
            ops=[{"type": "normalize", "params": {"mode": "minmax"}}],
        )
        
        # 等待完成（测试中同步等待）
        QTest.qWait(1000)
        self.assertTrue(any(r[0] == "progress" for r in received))
```

## 验证清单

- [ ] Pipeline 执行大输入时 UI 可操作
- [ ] 进度条实时更新
- [ ] 取消后恢复初始状态
- [ ] 执行完成后自动刷新预览

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`
