# Phase 3 Task 4

## 阶段

- Phase 3 / workspace-controllers-and-business-state

## 对应方案

- `docs/refactor/04-phase-3-workspace-controllers-and-business-state.md`

## 目标

- 为 `DigitizePage` 建立正式的 `WorkspaceController + WorkspaceState` 结构。
- 把数字化页的当前图片、当前曲线、自动识别、导出目标、校准上下文和交互缓冲状态从 `QWidget` 私有属性中收口。

## 本任务范围

- 新增 `DigitizeWorkspaceState/Controller`。
- 让 `DigitizePage` 的当前图片、当前曲线、自动识别、导出目标、校准上下文和交互缓冲由 `WorkspaceState` 持有。
- 保持现有数字化与导出行为不变。
- 补对应窄测。

## 验证

- `python3 -m unittest tests.test_digitize_workspace tests.test_refactor_guardrails`
- `python3 -m py_compile app/workspaces/digitize_workspace.py ui/pages/digitize_page.py tests/test_digitize_workspace.py`

## 完成判定

- `DigitizePage` 已存在正式的 workspace controller/state 结构。
- 数字化页关键业务状态不再只散落在 `QWidget` 私有属性中。
