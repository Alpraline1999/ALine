# Phase 1 Task 6

## 阶段

- Phase 1 / app-shell-and-runtime-boundaries

## 对应方案

- `docs/refactor/02-phase-1-app-shell-and-runtime-boundaries.md`

## 目标

- 开始把共享树中的项目数据命令从 `ProjectTreeWidget` 中抽到独立命令服务。
- 先迁移删除节点、新建子文件夹、新建数据集这三个最小切片。

## 本任务范围

- 新增 `ProjectTreeCommandService`。
- 让 `ProjectTreeWidget` 将 `_cmd_delete`、`_cmd_add_child_folder`、`_cmd_add_dataset_node` 委托给命令服务。
- 为命令服务补窄测。

## 不纳入本任务

- 不迁移导入、重命名、移动等其它命令。
- 不改变命令执行后的 UI 行为。

## 验证

- `python3 -m unittest tests.test_project_tree_command_service tests.test_project_tree_page_dispatcher tests.test_project_tree_builder tests.test_tree_action_dispatcher tests.test_app_runtime tests.test_refactor_guardrails`
- `python3 -m py_compile app/project_tree_command_service.py ui/widgets/project_tree.py tests/test_project_tree_command_service.py`

## 完成判定

- 这三类共享树命令不再由 `ProjectTreeWidget` 直接承载核心执行逻辑。
