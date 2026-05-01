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

第 1 步: 建立目录结构 + 提取最独立的测试 (ProjectTree, NavigationStack, HomePage, Onboarding)
第 2 步: 提取页面级测试
第 3 步: 提取主窗口测试
