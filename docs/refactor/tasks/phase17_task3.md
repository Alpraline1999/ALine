# Phase 17 Task 3

## 阶段

- Phase 17 / domain-flow-and-analytical-workbench-normalization

## 对应方案

- `docs/refactor/20-phase-17-domain-flow-and-analytical-workbench-normalization.md`

## 目标

- 收口 `processing/data_engine` 的 pipeline 执行编排，把线性执行和配对执行拆成更清晰的 helper。

## 本任务范围

- `processing/data_engine.py`

## 不纳入

- 算法行为重写
- 扩展协议改版
- 测试框架调整

## 验证

- 聚焦 `data_engine` 的 `py_compile`
- 跑扩展运行时与数据流窄测

## 完成判定

- `apply_pipeline_to_lines` 的执行分支更清晰。
- pipeline 结果与 warnings 行为保持不变。
