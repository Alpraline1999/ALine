# Phase 5 Task 3

## 阶段

- Phase 5 / cleanup-file-splitting-and-dead-path-removal

## 对应方案

- `docs/refactor/06-phase-5-cleanup-file-splitting-and-dead-path-removal.md`

## 目标

- 将 `ui/widgets/project_tree.py` 的通用常量与 helper 函数拆出为独立模块。
- 让项目树 widget 本体只保留行为实现，不再混杂基础配置与图标/排序工具。

## 本任务范围

- 新增 `ui/widgets/project_tree_support.py`。
- 将 `project_tree.py` 顶部的常量与通用 helper 移入新模块。
- 保持现有项目树行为不变。

## 验证

- `python3 -m unittest tests.test_refactor_guardrails`
- `python3 -m py_compile ui/widgets/project_tree.py ui/widgets/project_tree_support.py`

## 完成判定

- 项目树的基础常量与 helper 已与 widget 主体分离。
