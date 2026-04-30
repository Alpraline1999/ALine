# Phase 1 Task 12

## 阶段

- Phase 1 / app-shell-and-runtime-boundaries

## 对应方案

- `docs/refactor/02-phase-1-app-shell-and-runtime-boundaries.md`

## 目标

- 继续收口共享树剩余的直接写运行时状态交互。
- 本次聚焦节点重命名与源文件拖放到数字化的导入路径。

## 本任务范围

- 扩展 `ProjectTreeCommandService`，纳入：
  - 常规节点重命名
  - 统一的选择式重命名入口
  - 源文件导入到数字化
- 让 `ProjectTreeWidget.rename_selected_item`、`_on_item_changed` 与源文件拖放到数字化分支委托给服务或复用服务逻辑。
- 补对应窄测。

## 验证

- `python3 -m unittest tests.test_project_tree_command_service tests.test_project_tree_page_dispatcher tests.test_project_tree_builder tests.test_tree_action_dispatcher tests.test_app_runtime tests.test_refactor_guardrails`
- `python3 -m py_compile app/project_tree_command_service.py ui/widgets/project_tree.py tests/test_project_tree_command_service.py`

## 完成判定

- 共享树节点重命名不再由 `ProjectTreeWidget` 直接调用 `project_manager.rename_*`。
- 源文件拖放到数字化与菜单导入数字化共享同一条服务层执行逻辑。
