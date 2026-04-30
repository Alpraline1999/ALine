# Phase 3 Task 2

## 阶段

- Phase 3 / workspace-controllers-and-business-state

## 对应方案

- `docs/refactor/04-phase-3-workspace-controllers-and-business-state.md`

## 目标

- 落地 `AnalysisWorkspaceController/State`。
- 先收口分析页的输入选择、当前树选择和报告模板上下文。

## 本任务范围

- 新增 `AnalysisWorkspaceState/Controller`。
- 让 `AnalysisPage` 的已选输入、当前树选择、当前报告模板上下文由 `WorkspaceState` 持有。
- 让分析页共享树入口先经过 controller。
- 补对应窄测。

## 验证

- `python3 -m unittest tests.test_analysis_workspace tests.test_refactor_guardrails`
- `python3 -m py_compile app/workspaces/analysis_workspace.py ui/pages/analysis_page.py tests/test_analysis_workspace.py`

## 完成判定

- `AnalysisPage` 已存在正式的 workspace controller/state 结构。
- 分析页关键业务选择状态不再只散落在 QWidget 私有属性中。
