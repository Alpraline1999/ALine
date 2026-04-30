# Phase 7 Task 5

## 阶段

- Phase 7 / ui-state-performance-and-polish

## 对应方案

- `docs/refactor/08-phase-7-ui-state-performance-and-polish.md`

## 目标

- 将设置页里的纯 UI 延迟刷新标记归属到独立 view-state 模型。
- 保持扩展分类卡片高度刷新行为不变。

## 本任务范围

- 新增设置页 UI view-state。
- 将扩展分类 tab 高度刷新 pending 标记迁入 view-state。
- 保持现有交互行为不变。

## 验证

- `./.venv/bin/python -m unittest tests.test_settings_page_view_state tests.test_ui_smoke`
- `./.venv/bin/python -m py_compile ui/page_view_state.py ui/pages/settings_page.py tests/test_settings_page_view_state.py`

## 完成判定

- 设置页纯 UI 状态开始从页面杂项字段迁入独立 view-state。
