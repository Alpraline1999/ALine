# Phase 1 Task 3

## 阶段

- Phase 1 / app-shell-and-runtime-boundaries

## 对应方案

- `docs/refactor/02-phase-1-app-shell-and-runtime-boundaries.md`

## 目标

- 把共享树视图类从 `project_tree.py` 巨型文件中抽离为独立模块。
- 为后续 `ProjectTreeBuilder` 继续拆分保留更清晰的文件边界。

## 本任务范围

- 新增独立的 `ProjectTreeView` 模块。
- 调整 `ProjectTreeWidget` 对视图类的引用。
- 不改变共享树行为与拖放逻辑。

## 执行步骤

1. 建立任务文件。
2. 抽取 `ProjectTreeView` 到独立模块。
3. 更新 `project_tree.py` 导入与实例化位置。
4. 运行窄测和语法校验。
5. 形成检查点提交。

## 验证

- `python3 -m unittest tests.test_tree_action_dispatcher tests.test_app_runtime tests.test_refactor_guardrails`
- `python3 -m py_compile ui/widgets/project_tree.py ui/widgets/project_tree_view.py`

## 完成判定

- 共享树视图类不再内嵌在 `project_tree.py` 中。
- `ProjectTreeWidget` 仍能通过同一 API 驱动视图。
