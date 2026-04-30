# Phase 7 Task 1

## 阶段

- Phase 7 / ui-state-performance-and-polish

## 对应方案

- `docs/refactor/08-phase-7-ui-state-performance-and-polish.md`

## 目标

- 将页面里的纯 UI 状态归属到独立 view-state 模型。
- 保持业务状态对象不承担 splitter、tooltip、面板显隐等纯 UI 数据。

## 本任务范围

- 新增统一的页面 view-state 模块。
- 将图表页、分析页、数字化页的纯 UI 状态切换到 view-state。
- 保持现有交互行为不变。

## 验证

- `./.venv/bin/python -m unittest tests.test_refactor_guardrails tests.test_page_view_state tests.test_ui_smoke`
- `./.venv/bin/python -m py_compile ui/page_view_state.py ui/pages/chart_page.py ui/pages/analysis_page.py ui/pages/digitize_page.py tests/test_page_view_state.py`

## 完成判定

- 纯 UI 状态开始从页面杂项字段迁入独立 view-state。
