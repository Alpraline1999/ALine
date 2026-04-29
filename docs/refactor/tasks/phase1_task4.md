# Phase 1 Task 4

## 阶段

- Phase 1 / app-shell-and-runtime-boundaries

## 对应方案

- `docs/refactor/02-phase-1-app-shell-and-runtime-boundaries.md`

## 目标

- 把共享树刷新 orchestration 从 `ProjectTreeWidget` 中抽到独立的 builder 对象。
- 在不改树节点生成细节的前提下，先建立 `ProjectTreeBuilder` 这个显式边界。

## 本任务范围

- 新增 `ProjectTreeBuilder`。
- 让 `ProjectTreeWidget.refresh()` 委托 builder 执行整体重建流程。
- 为 builder 的 orchestration 增加窄测。

## 不纳入本任务

- 不在本任务中重写 `_build_children` 的细粒度实现。
- 不修改共享树行为、过滤逻辑、拖放逻辑。

## 验证

- `python3 -m unittest tests.test_project_tree_builder tests.test_tree_action_dispatcher tests.test_app_runtime tests.test_refactor_guardrails`
- `python3 -m py_compile ui/widgets/project_tree.py ui/widgets/project_tree_builder.py`

## 完成判定

- `ProjectTreeWidget.refresh()` 不再内联完整重建流程。
- 共享树重建入口存在独立 builder 对象。
