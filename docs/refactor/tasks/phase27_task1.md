# Phase 27 Task 1

## 阶段

- Phase 27 / ui-theme-and-paint-regression-audit

## 对应方案

- `docs/refactor/32-phase-27-ui-theme-and-paint-regression-audit.md`

## 目标

- 先做主题切换链路、项目树绘制和 settings 主题一致性的全面检查，再修复已确认的运行时回归与性能热点。

## 本任务范围

- `ui/main_window.py`
- `ui/widgets/project_tree.py`
- `ui/widgets/project_tree_support.py`
- `ui/pages/settings_page.py`
- `ui/pages/chart_page.py`
- `ui/pages/data_page.py`
- `ui/pages/process_page.py`
- `ui/pages/analysis_page.py`
- `tests/test_ui.py`
- `tests/test_page_support_modules.py`

## 不纳入

- 新一轮视觉改版
- 无证据的大规模 UI 重写
- 与主题无关的业务功能开发

## 验证

- `./.venv/bin/python -m py_compile ui/main_window.py ui/widgets/project_tree.py ui/widgets/project_tree_support.py ui/pages/settings_page.py ui/pages/chart_page.py ui/pages/data_page.py ui/pages/process_page.py ui/pages/analysis_page.py tests/test_ui.py tests/test_page_support_modules.py`
- `./.venv/bin/python -m unittest tests.test_page_support_modules.TestPageSupportModules`
- `./.venv/bin/python -m unittest tests.test_ui.TestChartPageV3 tests.test_ui.TestDataPage tests.test_ui.TestProcessPage tests.test_ui.TestAnalysisPage`

## 完成判定

- 主题切换链路、项目树绘制安全和 settings 主题一致性都已建立明确的检查与回归护栏。
- 本阶段的运行时回归和性能卡顿问题已在窄测范围内被复现、修复或明确记录。
