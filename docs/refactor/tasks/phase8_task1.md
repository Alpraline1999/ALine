# Phase 8 Task 1

## 阶段

- Phase 8 / large-curve-performance-and-extension-optimization

## 对应方案

- `docs/refactor/10-phase-8-large-curve-performance-and-extension-optimization.md`

## 目标

- 固化大曲线/大数据量场景的 profiling 样本和性能热点地图。
- 完成首批不改主数据模型的局部性能优化。
- 为 `Phase 9` 的数组化迁移提供证据，而不是直接跨阶段改写数据表示。

## 本任务范围

- 建立图表渲染、分析、处理、数字化、扩展执行的窄范围性能样本。
- 标记主线程阻塞、重复重绘、重复转换和重复拷贝热点。
- 仅在已有证据支持下实施局部抽样、缓存、后台执行或局部刷新优化。

## 验证

- 以窄范围性能样本和定向回归测试为准。
- 不做全量回归测试。

## 完成判定

- 已形成可复用的性能样本集。
- 已识别 `Phase 9` 需要收口的主数据转换热点。
- 当前任务内没有越界进入扩展 API 重构。
