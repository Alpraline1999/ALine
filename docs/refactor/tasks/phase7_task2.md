# Phase 7 Task 2

## 阶段

- Phase 7 / ui-state-performance-and-polish

## 对应方案

- `docs/refactor/08-phase-7-ui-state-performance-and-polish.md`

## 目标

- 将主窗口里的纯 UI 状态归属到独立 view-state 模型。
- 保持项目树面板宽度、隐藏状态和共享扩展面板显隐行为不变。

## 本任务范围

- 新增主窗口 UI view-state。
- 将 `MainWindow` 的树面板宽度、树面板隐藏状态、共享扩展面板显隐迁入 view-state。
- 保持现有交互行为不变。

## 验证

- `./.venv/bin/python -m unittest tests.test_main_window_view_state tests.test_ui_smoke`
- `./.venv/bin/python -m py_compile ui/page_view_state.py ui/main_window.py tests/test_main_window_view_state.py`

## 完成判定

- 主窗口纯 UI 状态开始从页面/窗口杂项字段迁入独立 view-state。
