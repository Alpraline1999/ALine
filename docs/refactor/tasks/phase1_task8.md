# Phase 1 Task 8

## 阶段

- Phase 1 / app-shell-and-runtime-boundaries

## 对应方案

- `docs/refactor/02-phase-1-app-shell-and-runtime-boundaries.md`

## 目标

- 继续把共享树批量与虚拟节点命令迁入命令服务。
- 本次纳入虚拟节点删除、批量删除、批量移动。

## 本任务范围

- 扩展 `ProjectTreeCommandService`。
- 让 `ProjectTreeWidget` 将 `_cmd_delete_virtual`、`_cmd_delete_batch`、`_cmd_move_batch` 委托给服务执行。
- 补对应窄测。

## 验证

- `python3 -m unittest tests.test_project_tree_command_service tests.test_project_tree_page_dispatcher tests.test_project_tree_builder tests.test_tree_action_dispatcher tests.test_app_runtime tests.test_refactor_guardrails`
- `python3 -m py_compile app/project_tree_command_service.py ui/widgets/project_tree.py tests/test_project_tree_command_service.py`

## 完成判定

- 这三类共享树命令不再由 `ProjectTreeWidget` 直接承载核心执行逻辑。
