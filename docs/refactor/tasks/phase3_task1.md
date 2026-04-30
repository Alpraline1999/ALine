# Phase 3 Task 1

## 阶段

- Phase 3 / workspace-controllers-and-business-state

## 对应方案

- `docs/refactor/04-phase-3-workspace-controllers-and-business-state.md`

## 目标

- 为 `DataPage` 与 `ProcessPage` 建立首批 `WorkspaceController + WorkspaceState` 结构。
- 先收口两页最核心的业务选择状态与共享树动作入口。

## 本任务范围

- 新增 `DataWorkspaceState/Controller`。
- 新增 `ProcessWorkspaceState/Controller`。
- 让 `DataPage` 的当前树选择/预览关键状态改由 `DataWorkspaceState` 持有。
- 让 `ProcessPage` 的已选输入、当前 pipeline、输出批次、保存目标等关键状态改由 `ProcessWorkspaceState` 持有。
- 让两页的共享树动作入口先经过 controller。
- 补对应窄测。

## 验证

- `python3 -m unittest tests.test_data_workspace tests.test_process_workspace tests.test_refactor_guardrails`
- `python3 -m py_compile app/workspaces/data_workspace.py app/workspaces/process_workspace.py ui/pages/data_page.py ui/pages/process_page.py tests/test_data_workspace.py tests/test_process_workspace.py`

## 完成判定

- `DataPage` 与 `ProcessPage` 已经存在正式的 workspace controller/state 结构。
- 两页的关键业务选择状态不再直接以裸散私有属性作为唯一状态源。
