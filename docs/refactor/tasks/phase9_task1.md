# Phase 9 Task 1

## 阶段

- Phase 9 / runtime-array-data-model

## 对应方案

- `docs/refactor/11-phase-9-runtime-array-data-model.md`

## 目标

- 定义运行时曲线主数据的数组后端类型和适配边界。
- 明确哪些数值曲线路径需要改为数组主数据，哪些边界继续保持可序列化结构。

## 本任务范围

- 设计 `CurveBuffer` / `SeriesArrayView` 或等价对象。
- 盘点 `list(point)`、`x/y`、`series payload` 的重复转换热点。
- 选择首批迁移链路并定义回写与缓存策略。

## 验证

- 以热路径审查、窄范围性能样本和定向回归测试为准。
- 不做全量回归测试。

## 完成判定

- 数组主数据对象与适配层边界已经明确。
- 至少一条高收益链路可进入迁移实施。
- 未把非数值集合错误纳入数组化范围。
