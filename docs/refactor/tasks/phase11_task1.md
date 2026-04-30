# Phase 11 Task 1

## 阶段

- Phase 11 / large-curve-hot-path-and-memory-hardening

## 对应方案

- `docs/refactor/13-phase-11-large-curve-hot-path-and-memory-hardening.md`

## 目标

- 收口大曲线与大数据量主链路的重复物化和重复复制。
- 优先优化运行时数组视图、批量输入和热路径转换。

## 本任务范围

- 优化 `core.curve_data` 与 `core.line_tools` 的曲线批量转换路径。
- 优化扩展运行时中与大曲线相关的最小热路径。
- 盘点并收缩少量高频 `list(...)` 边界转换。

## 不纳入

- UI 超大文件拆分
- 扩展协议再次重构
- 代码规范和 UI 一致性收尾

## 验证

- 以窄范围单元测试和小样本运行时验证为准。
- 不做全量回归测试。

## 完成判定

- 大曲线热路径至少有一处明显的重复转换被收口。
- 相关窄测通过。
- 性能边界和回退策略已记录。
