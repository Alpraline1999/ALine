# Phase 13 Task 1

## 阶段

- Phase 13 / codebase-normalization-and-ui-consistency

## 对应方案

- `docs/refactor/15-phase-13-codebase-normalization-and-ui-consistency.md`

## 目标

- 盘点 Phase 12 收尾后仍存在的兼容转发、重复 helper、状态呈现不一致和导出面漂移。
- 先从高噪声、低风险项开始收口，为后续一致性整理建立清晰边界。

## 本任务范围

- 盘点仍在使用的兼容转发层、重复适配器和重复格式化逻辑。
- 梳理 UI 中空态、错态、加载态和完成态的文案与 token 风格差异。
- 只对局部高噪声债务做小范围收口，不触碰 Phase 12 刚稳定的页面拆分边界。

## 不纳入

- 新业务功能
- 页面再次大拆分
- 大规模视觉改版

## 验证

- 以针对清理点的窄测为准。
- 不做全量回归测试。

## 完成判定

- 至少完成一组兼容层或重复 helper 的明确收口。
- UI 一致性相关的低风险修复已经落地，并有对应窄测或结构校验。
