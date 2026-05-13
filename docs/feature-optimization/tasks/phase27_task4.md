# Phase 27 Task 4: 大文件导入进度反馈

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`，阶段 `Phase 27`

## 目标

为大数据文件（>10MB CSV/Excel）的导入过程添加进度反馈，避免 UI 冻结。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `core/data_operations.py` | 提高逐行解析的更新频率 |
| `ui/dialogs/import_dialog.py` | 集成进度条和取消按钮 |

## 实施方案

### Step 1: DataOperations 支持进度回调

```python
# core/data_operations.py
from typing import Callable, Optional

ProgressCallback = Callable[[int, int, str], None]  # current, total, status

def import_csv(
    file_path: str,
    *,
    on_progress: Optional[ProgressCallback] = None,
) -> List[DataSeries]:
    """从 CSV / TXT / DAT / TSV 导入。
    
    Args:
        file_path: 文件路径
        on_progress: 进度回调 (cur, total, status)
    """
    # ... 读取全部行
    lines = [l for l in f if l.strip() and not l.strip().startswith("#")]
    total = len(lines)
    
    if on_progress:
        on_progress(0, total, "检测分隔符...")
    
    sep = _detect_sep(data_lines[0])
    # ... 解析数据
    
    cols: List[List[float]] = [[] for _ in range(n)]
    for i, line in enumerate(data_rows):
        if not line.strip():
            continue
        cells = split(line)
        for j in range(n):
            try:
                cols[j].append(float(cells[j]) if j < len(cells) else float("nan"))
            except ValueError:
                cols[j].append(float("nan"))
        
        # 每 100 行或 1% 进度报告一次
        if on_progress and (i % max(1, total // 100) == 0 or i == total - 1):
            on_progress(i + 1, total, f"解析第 {i+1}/{total} 行")
    
    return _cols_to_series(cols, headers, stem)
```

### Step 2: ImportDialog 集成

```python
# ui/dialogs/import_dialog.py
class ImportDialog:
    def _do_import(self, paths: List[str]):
        self._progress_bar.setVisible(True)
        self._progress_bar.setMaximum(100)
        self._cancel_btn.setVisible(True)
        self._total_files = len(paths)
        
        for file_idx, path in enumerate(paths):
            if self._cancelled:
                break
            
            self._status_label.setText(f"导入文件 {file_idx+1}/{self._total_files}: {Path(path).name}")
            
            try:
                from core.data_operations import import_csv
                series = import_csv(
                    path,
                    on_progress=lambda cur, total, status: 
                        self._update_progress(file_idx, cur, total, status),
                )
                # ... 处理结果
            except Exception as e:
                self._show_error(str(e))
    
    def _update_progress(self, file_idx, cur, total, status):
        overall = int((file_idx / self._total_files) * 100 + 
                      (cur / total) * (100 / self._total_files))
        self._progress_bar.setValue(overall)
        self._status_label.setText(f"[{file_idx+1}/{self._total_files}] {status}")
```

## 验证清单

- [ ] 导入 50MB CSV 时 UI 不冻结
- [ ] 进度条平滑更新
- [ ] 取消按钮可中断导入
- [ ] 导入完成后的结果正常

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`
