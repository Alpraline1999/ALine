# Phase 7 Task 6

## 阶段

- Phase 7 / ui-state-performance-and-polish

## 对应方案

- `docs/refactor/08-phase-7-ui-state-performance-and-polish.md`

## 目标

- 修复设置页在重构后的兼容回归。
- 用窄范围验收测试复核当前重构交付状态。

## 本任务范围

- 修复 `SettingsPage.refresh_templates()` 在无旧模板列表字段时的崩溃。
- 为设置页模板刷新补充独立回归测试。
- 运行覆盖各阶段边界的窄范围验收测试，不做全量回归。

## 验证

- `./.venv/bin/python -m unittest tests.test_settings_page_refresh tests.test_ui_smoke`
- `./.venv/bin/python -m unittest tests.test_refactor_phase0 tests.test_refactor_guardrails tests.test_architecture_guardrails tests.test_app_runtime tests.test_project_session tests.test_project_repository tests.test_project_migration_service tests.test_project_tree_service tests.test_project_asset_service tests.test_project_tree_builder tests.test_project_tree_page_dispatcher tests.test_tree_action_dispatcher tests.test_extension_bootstrap tests.test_page_support_modules tests.test_data_workspace tests.test_chart_workspace tests.test_process_workspace tests.test_analysis_workspace tests.test_digitize_workspace tests.test_page_view_state tests.test_main_window_view_state tests.test_process_page_view_state tests.test_settings_page_view_state tests.test_digitize_auto_detect tests.test_ui_smoke`
- `./.venv/bin/python -m py_compile ui/pages/settings_page.py tests/test_settings_page_refresh.py`

## 完成判定

- 设置页模板刷新兼容路径不再崩溃。
- 当前重构阶段已有一组可执行的窄范围验收结果。
