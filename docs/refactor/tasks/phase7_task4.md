# Phase 7 Task 4

## 阶段

- Phase 7 / ui-state-performance-and-polish

## 对应方案

- `docs/refactor/08-phase-7-ui-state-performance-and-polish.md`

## 目标

- 将处理页里的纯 UI 状态归属到独立 view-state 模型。
- 保持处理页扩展面板与 splitter 的交互行为不变。

## 本任务范围

- 新增处理页 UI view-state。
- 将处理页的扩展面板显隐、扩展面板宽度、selected input splitter 手动调整标记迁入 view-state。
- 保持现有交互行为不变。

## 验证

- `./.venv/bin/python -m unittest tests.test_process_page_view_state tests.test_ui_smoke`
- `./.venv/bin/python -m py_compile ui/page_view_state.py ui/pages/process_page.py tests/test_process_page_view_state.py`

## 完成判定

- 处理页纯 UI 状态开始从页面杂项字段迁入独立 view-state。
