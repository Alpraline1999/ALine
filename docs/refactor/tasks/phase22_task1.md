# Phase 22 Task 1

## 阶段

- Phase 22 / large-workspace-performance-and-data-virtualization

## 对应方案

- `docs/refactor/26-phase-22-large-workspace-performance-and-data-virtualization.md`

## 目标

- 先建立大工作区与超大曲线的 profiling 样本和最小性能基线，再决定后续虚拟化/渐进渲染切点。

## 本任务范围

- profiling / benchmark fixture
- 大曲线或大工作区样本入口
- 直接相关的性能阈值记录

## 不纳入

- 全仓 list-to-numpy 重写
- GPU 渲染器替换
- 全量回归测试

## 验证

- 命中的 profiling 脚本或最小 benchmark
- 相关窄测或样本驱动检查

## 完成判定

- 至少一组可复用的大曲线/大工作区样本被固定下来。
- 性能基线不是临时手工导入，而是可复跑的 fixture。
