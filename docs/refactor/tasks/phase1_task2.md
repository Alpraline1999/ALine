# Phase 1 Task 2

## 阶段

- Phase 1 / app-shell-and-runtime-boundaries

## 对应方案

- `docs/refactor/02-phase-1-app-shell-and-runtime-boundaries.md`

## 目标

- 让共享树动作先经过显式命令分发，而不是直接把 `(kind, node_id)` 信号送进 `MainWindow` 业务分支。
- 为后续 `ProjectTreeView + Builder + Dispatcher` 三段式拆分保留稳定分发接口。

## 本任务范围

- 新增 `ProjectTreeActionDispatcher`。
- 让树的 `node_selected/node_activated` 先转换为 `AppCommand(TreeCommand(NodeRef))`。
- 让 `MainWindow` 通过命令对象接收树动作。
- 为分发器补窄测。

## 不纳入本任务

- 不重写共享树内部构建逻辑。
- 不在本任务中拆出完整 `ProjectTreeBuilder`。
- 不改变页面现有业务行为与路由结果。

## 执行步骤

1. 新建任务文件，记录本次结构切片范围。
2. 新增 `ProjectTreeActionDispatcher`，收口树动作到显式命令。
3. 调整 `MainWindow` 连接方式与树命令处理入口。
4. 补充分发器窄测。
5. 运行 `Phase 1` 窄测与 `Phase 0` 护栏测试。
6. 按 `important-change-commit` 形成新的检查点提交。

## 验证

- `python3 -m unittest tests.test_tree_action_dispatcher tests.test_app_runtime tests.test_refactor_guardrails`

## 提交节点

- `checkpoint`：共享树动作进入显式命令分发。

## 完成判定

- `MainWindow` 不再直接接收原始树信号作为主要边界。
- 树选择/激活动作存在显式命令对象。
- 窄测能够独立验证该分发切片。
