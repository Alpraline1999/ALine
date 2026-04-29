# Phase 1 Task 1

## 阶段

- Phase 1 / app-shell-and-runtime-boundaries

## 对应方案

- `docs/refactor/02-phase-1-app-shell-and-runtime-boundaries.md`

## 目标

- 建立 `AppContext`、基础命令模型和事件模型。
- 为 `MainWindow` 壳层化提供首个稳定结构切片。
- 不改变页面业务算法，只增加新的边界承载层。

## 本任务范围

- 新增 `AppContext`。
- 新增 `AppCommand`、`TreeCommand`、`SessionEvent`、`NodeRef` 基础模型。
- 新增轻量事件总线，先承载类型化事件发布与订阅能力。
- 在不改业务行为的前提下，让 `MainWindow` 持有 `AppContext`。
- 为新的上下文与消息模型补窄测。

## 不纳入本任务

- 不拆 `ProjectManager` 内部逻辑。
- 不迁移页面内部业务状态。
- 不在本任务中完成共享树三段式拆分。
- 不在本任务中清零 `MainWindow` 旧的跨页私有调用。

## 执行步骤

1. 建立 `AppContext` 及运行时适配结构，先包裹现有单例。
2. 建立 `NodeRef`、`AppCommand`、`TreeCommand`、`SessionEvent` 消息模型。
3. 建立轻量事件总线并补最小单元测试。
4. 让 `MainWindow` 在构造时创建并持有 `AppContext`。
5. 运行 Phase 1 窄测，验证新的边界对象可独立工作。
6. 按 `important-change-commit` 形成 `Phase 1 / start` 提交。

## 验证

- `python3 -m unittest tests.test_app_runtime`
- `python3 -m unittest tests.test_refactor_guardrails`

## 提交节点

- `start`：`AppContext`、消息模型、事件总线落地并接入 `MainWindow`。
- `checkpoint`：`MainWindow` 壳层化，移除一批跨页私有调用。
- `end`：共享树三段式边界落地并满足阶段验收标准。

## 完成判定

- 新的运行时上下文和消息模型已存在稳定模块。
- `MainWindow` 已能持有并暴露唯一的 `AppContext`。
- 相关窄测通过，且未扩大到全量回归。
