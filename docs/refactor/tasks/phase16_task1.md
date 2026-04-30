# Phase 16 Task 1

## 阶段

- Phase 16 / static-quality-and-reliability-hardening

## 对应方案

- `docs/refactor/19-phase-16-static-quality-and-reliability-hardening.md`

## 目标

- 先收口当前工作集里明确暴露的导入噪声、重复定义和一个匿名排序回调。

## 本任务范围

- `ui/pages/analysis_page.py`
- `ui/pages/digitize_page.py`
- `ui/widgets/image_viewer.py`

## 不纳入

- 全仓库 `ruff --fix`
- 异常策略分级
- 大规模 UI 结构调整

## 验证

- 聚焦这几个文件的 `py_compile`
- 只跑与修改面直接相关的窄测

## 完成判定

- 这批文件中明确命中的 `F401` / `F841` / `E731` / `F811` 问题被清理。
- 没有引入新行为差异。
