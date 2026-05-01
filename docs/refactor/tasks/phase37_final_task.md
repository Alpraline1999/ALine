# Phase 37 最终执行: 超大测试文件拆分 + UI 一致性复核

## 目标

1. 拆分 tests/test_ui.py (11050 行，22 个类)
2. 拆分 tests/test_backend.py (3759 行)
3. 更新 structure_check.py 使门禁通过

## 测试拆分计划

tests/test_ui.py → 按页面/模块拆分为:
- tests/pages/test_data_page.py
- tests/pages/test_chart_page.py
- tests/pages/test_process_page.py
- tests/pages/test_analysis_page.py
- tests/pages/test_digitize_page.py
- tests/pages/test_settings_page.py
- tests/pages/test_home_page.py
- tests/widgets/test_project_tree.py
- tests/widgets/test_navigation_stack.py
- tests/widgets/test_extension_config_panel.py
- tests/widgets/test_extension_options_form.py
- tests/widgets/test_onboarding.py  (PageOnboardingController)
- tests/test_main_window.py
- tests/test_signal_workflows.py
- tests/test_import_dialog.py

第 1 步: 建立目录结构 + 提取最独立的测试 (HomePage, Onboarding, FocusCommit) — 已完成
第 2 步: 提取页面级测试 — 转入功能优化阶段
第 3 步: 提取主窗口测试 — 转入功能优化阶段

### 遗留 monolith 确认

以下 6 个大文件不下沉、不再继续拆分，统一记为"遗留 monolith，功能优化阶段优先处理":

- ui/pages/data_page.py (4906 行)
- ui/pages/chart_page.py (4244 行)
- ui/pages/digitize_page.py (3601 行)
- ui/pages/analysis_page.py (2897 行)
- ui/pages/settings_page.py (1715 行)
- core/project_manager.py (2047 行)

以下测试文件不再继续拆分，转入功能优化阶段：
- tests/test_ui.py (10699 行, 已提取 3 个类)
- tests/test_backend.py (3759 行)
