# Phase 15 Task 2

## 阶段

- Phase 15 / monolith-decomposition-and-shared-widget-extraction

## 对应方案

- `docs/refactor/18-phase-15-monolith-decomposition-and-shared-widget-extraction.md`

## 目标

- 对共享 widget 进行第二轮实质性深拆。
- 将 `image_viewer` 的 overlay 数据结构抽到独立模块，减少主文件职责密度。

## 本任务范围

- `ui/widgets/image_viewer.py`
- 新增的 overlay 支撑模块

## 不纳入

- `project_tree` 全面重写
- `extension_options_form` 深拆
- 业务流程重构
- 视觉重设计

## 验证

- 先做 `py_compile`，再做 `image_viewer` 相关窄测。
- 不做全量回归测试。

## 完成判定

- `image_viewer` 主文件职责收窄，overlay 数据结构有单独归属。
- 与 DataPage 的第一轮拆分一起，形成至少两个 monolith 的实质性深拆。
