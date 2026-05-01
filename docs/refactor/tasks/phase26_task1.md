# Phase 26 Task 1

## 阶段

- Phase 26 / project-tree-and-ui-interaction-surface-decomposition

## 对应方案

- `docs/refactor/31-phase-26-project-tree-and-ui-interaction-surface-decomposition.md`

## 目标

- 降低主题切换时的同步重绘卡顿，并继续收口项目树与页面交互 surface。

## 本任务范围

- `ui/main_window.py`
- `ui/pages/chart_page.py`
- `ui/pages/data_page.py`
- `ui/pages/process_page.py`
- `ui/pages/analysis_page.py`
- `tests/test_ui.py`

## 不纳入

- 主窗口导航重写
- 大规模页面拆分
- 无证据的性能重构

## 验证

- `./.venv/bin/python -m py_compile ui/main_window.py ui/pages/chart_page.py ui/pages/data_page.py ui/pages/process_page.py ui/pages/analysis_page.py tests/test_ui.py`
- `./.venv/bin/python -m unittest tests.test_ui.TestChartPage tests.test_ui.TestDataPage tests.test_ui.TestProcessPage tests.test_ui.TestAnalysisPage`

## 完成判定

- 主题切换不再同步触发所有重图重绘。
- 项目树与页面目标解析保持一致且有窄测覆盖。
