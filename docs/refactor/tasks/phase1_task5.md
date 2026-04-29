# Phase 1 Task 5

## 阶段

- Phase 1 / app-shell-and-runtime-boundaries

## 对应方案

- `docs/refactor/02-phase-1-app-shell-and-runtime-boundaries.md`

## 目标

- 把共享树中所有“发给页面/壳层”的选择与激活动作统一收口到独立 dispatcher。
- 为后续彻底拆分 `ProjectTreeActionDispatcher` 业务边界提供单一发射入口。

## 本任务范围

- 新增共享树页面动作 dispatcher。
- 让 `ProjectTreeWidget` 的基础 `node_selected/node_activated` 发射与关键跨页动作先走 dispatcher。
- 为 dispatcher 补窄测。

## 不纳入本任务

- 不改共享树对项目数据的 CRUD 逻辑。
- 不改 `MainWindow` 的命令处理结果。

## 验证

- `python3 -m unittest tests.test_project_tree_page_dispatcher tests.test_project_tree_builder tests.test_tree_action_dispatcher tests.test_app_runtime tests.test_refactor_guardrails`
- `python3 -m py_compile ui/widgets/project_tree.py ui/widgets/project_tree_page_dispatcher.py tests/test_project_tree_page_dispatcher.py`

## 完成判定

- 共享树到壳层/页面的基础动作发射入口只保留 dispatcher。
