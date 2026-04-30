# Phase 22 Task 3

## 阶段

- Phase 22 / large-workspace-performance-and-data-virtualization

## 对应方案

- `docs/refactor/26-phase-22-large-workspace-performance-and-data-virtualization.md`

## 目标

- 收口大批量导出链路的临时复制，改为按需迭代和流式写出，降低峰值内存和主线程阻塞。

## 本任务范围

- `core/exporter.py`
- `tests/test_exporter_streaming.py`

## 不纳入

- 全量 UI 回归测试
- 项目文件格式重写
- 全仓 list-to-numpy 重写

## 验证

- `./.venv/bin/python -m py_compile core/exporter.py tests/test_exporter_streaming.py`
- `./.venv/bin/python -m unittest tests.test_exporter_streaming`

## 完成判定

- CSV / TXT / 剪贴板 / XML 导出热路径不再依赖 `_get_rows()` 先物化整批 rows。
- 导出侧仍保持既有输出格式与顺序。
