# Phase 23 Task 1

## 阶段

- Phase 23 / runtime-regression-and-contract-guardrails

## 对应方案

- `docs/refactor/28-phase-23-runtime-regression-and-contract-guardrails.md`

## 目标

- 清理已确认的运行时回归和死代码，给 late-stage refactor 补最小契约护栏。

## 本任务范围

- `core/extension_api.py`
- `ui/pages/analysis_page.py`
- `ui/pages/process_page.py`
- `ui/widgets/project_tree.py`
- `tests/test_ui.py`

## 不纳入

- 大规模页面拆分
- 全量 UI 回归
- 性能算法重写

## 验证

- `./.venv/bin/python -m py_compile core/extension_api.py ui/pages/analysis_page.py ui/pages/process_page.py ui/widgets/project_tree.py tests/test_ui.py`
- `./.venv/bin/python -m unittest tests.test_ui.TestProjectTreeWidget tests.test_ui.TestAnalysisPage`

## 完成判定

- 运行时回归护栏与已确认死代码清理完成。
- 页面 state proxy 不再因 late-stage refactor 漏接而报错。
