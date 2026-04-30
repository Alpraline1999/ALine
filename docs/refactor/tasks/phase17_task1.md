# Phase 17 Task 1

## 阶段

- Phase 17 / domain-flow-and-analytical-workbench-normalization

## 对应方案

- `docs/refactor/20-phase-17-domain-flow-and-analytical-workbench-normalization.md`

## 目标

- 先把 `analysis_engine` 里最重的一个结果装配分支拆到独立 helper，收口分析工作台的编排逻辑。

## 本任务范围

- `core/analysis_engine.py`

## 不纳入

- 新分析算法
- 导入/导出流程重写
- 测试框架改造

## 验证

- 聚焦 `analysis_engine` 的 `py_compile`
- 跑 `tests/test_backend.py` 中与 analysis 相关的窄测

## 完成判定

- `run_analysis` 少一段明显的长分支装配逻辑。
- `curve_fit` 的结果装配有独立 helper，行为不变。
