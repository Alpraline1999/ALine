# Phase 10 Task 1

## 阶段

- Phase 10 / extension-runtime-and-api-hardening

## 对应方案

- `docs/refactor/12-phase-10-extension-runtime-and-api-hardening.md`

## 目标

- 审计当前扩展接口和扩展运行时边界。
- 明确扩展 runtime 模块拆分、能力声明和数组原生输入契约。

## 本任务范围

- 识别 `core.extension_api` 中的 contracts / registry / loader / invoker / report / compatibility 混合职责。
- 明确 legacy handler 与新 runtime contract 的桥接策略。
- 规划内置扩展的迁移批次和验收样本。

## 验证

- 以扩展运行时窄测、架构扫描和定向回归测试为准。
- 不做全量回归测试。

## 完成判定

- `Phase 10` 的模块边界和迁移顺序已经清晰。
- 扩展接口的优化/重构必要性已经落实为正式阶段方案。
- legacy 兼容层的保留范围与退役方向已明确。
