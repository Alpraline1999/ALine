# Phase 3 Task 5

## 阶段

- Phase 3 / workspace-controllers-and-business-state

## 对应方案

- `docs/refactor/04-phase-3-workspace-controllers-and-business-state.md`

## 目标

- 收口 `ChartPage` 与 `DigitizePage` 的残余业务状态引用。
- 确认页面类只保留视图绑定和纯 UI 逻辑。

## 本任务范围

- 检查并收口两页中剩余的业务态读写入口。
- 保持 `WorkspaceController + WorkspaceState` 作为唯一业务态源。
- 完成 Phase 3 最后一次窄验证。

## 验证

- `python3 -m unittest tests.test_chart_workspace tests.test_digitize_workspace tests.test_refactor_guardrails`
- `python3 -m py_compile app/workspaces/chart_workspace.py app/workspaces/digitize_workspace.py ui/pages/chart_page.py ui/pages/digitize_page.py`

## 完成判定

- `ChartPage` 与 `DigitizePage` 的业务态都通过 workspace state 管理。
- Phase 3 的五个页面工作区结构已全部落地。
