# Phase 3 Task 3

## 阶段

- Phase 3 / workspace-controllers-and-business-state

## 对应方案

- `docs/refactor/04-phase-3-workspace-controllers-and-business-state.md`

## 目标

- 为 `ChartPage` 建立正式的 `WorkspaceController + WorkspaceState` 结构。
- 把图表页的曲线、样式、图形状态、扩展状态和共享树选择状态从 `QWidget` 私有属性中收口。

## 本任务范围

- 新增 `ChartWorkspaceState/Controller`。
- 让 `ChartPage` 的图表数据、曲线样式、图形状态、扩展状态、样式目标和共享树选择由 `WorkspaceState` 持有。
- 保持现有绘图和样式交互行为不变。
- 补对应窄测。

## 验证

- `python3 -m unittest tests.test_chart_workspace tests.test_refactor_guardrails`
- `python3 -m py_compile app/workspaces/chart_workspace.py ui/pages/chart_page.py tests/test_chart_workspace.py`

## 完成判定

- `ChartPage` 已存在正式的 workspace controller/state 结构。
- 图表页核心业务状态不再只散落在 `QWidget` 私有属性中。
