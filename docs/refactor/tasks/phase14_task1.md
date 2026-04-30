# Phase 14 Task 1

## 阶段

- Phase 14 / redundancy-elimination-and-architectural-consistency

## 对应方案

- `docs/refactor/17-phase-14-redundancy-elimination-and-architectural-consistency.md`

## 目标

- 收口 `core.extension_api` 与 `core.extension_runtime` 的重复 handler / normalize 实现。
- 固定 `core.extension_invoker` 为受控导入边界，减少调用方直接触达重复实现的风险。

## 本任务范围

- 盘点 `core/extension_api.py` 与 `core/extension_runtime.py` 中重复的 handler 实现。
- 调整 `processing/data_engine.py` 与相关测试中的导入边界。
- 保持现有行为不变，只做单源收口，不扩展到 ProjectManager、matplotlib bootstrap 或 DataPage。

## 不纳入

- `ProjectManager` 备份服务化
- matplotlib 启动入口统一
- `core/ai` 转发层清理
- `DataPage` 前提整理
- 大规模静态清理

## 验证

- 先做 `py_compile`，再做与扩展运行时和处理链路直接相关的窄测。
- 不做全量回归测试。

## 完成判定

- 处理/分析/绘图/数字化扩展 handler 的重复实现只保留一份权威来源。
- 调用方导入路径明确，且现有窄测通过。
- 为后续 Phase 14 的其他子阶段保留清晰边界。
