# Phase 1 Task 11

## 阶段

- Phase 1 / app-shell-and-runtime-boundaries

## 对应方案

- `docs/refactor/02-phase-1-app-shell-and-runtime-boundaries.md`

## 目标

- 收口共享树剩余的全局资源命令与数据文件导入命令。
- 让共享树菜单入口与源文件导入入口继续向 `ProjectTreeCommandService` 收敛。

## 本任务范围

- 扩展 `ProjectTreeCommandService`，纳入：
  - 重命名全局资源
  - 删除全局资源
  - 导入数据文件
- 让 `ProjectTreeWidget` 将 `_cmd_rename_global`、`_cmd_delete_global`、`_cmd_import_data_file` 委托给服务执行。
- 让源文件拖放到数据集的导入路径复用同一条命令服务逻辑。
- 补对应窄测。

## 验证

- `python3 -m unittest tests.test_project_tree_command_service tests.test_project_tree_page_dispatcher tests.test_project_tree_builder tests.test_tree_action_dispatcher tests.test_app_runtime tests.test_refactor_guardrails`
- `python3 -m py_compile app/project_tree_command_service.py ui/widgets/project_tree.py tests/test_project_tree_command_service.py`

## 完成判定

- 这三类共享树命令不再由 `ProjectTreeWidget` 直接承载核心执行逻辑。
- 源文件转数据文件的菜单入口与拖放入口共享同一条服务层执行路径。
