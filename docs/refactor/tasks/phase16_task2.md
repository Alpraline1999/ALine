# Phase 16 Task 2

## 阶段

- Phase 16 / static-quality-and-reliability-hardening

## 对应方案

- `docs/refactor/19-phase-16-static-quality-and-reliability-hardening.md`

## 目标

- 清理 `process_page` 当前暴露的未用导入噪声，继续推进 `F401` 收口。

## 本任务范围

- `ui/pages/process_page.py`

## 不纳入

- `chart_page` 全面清理
- 异常策略重构
- 业务逻辑调整

## 验证

- 聚焦 `process_page` 的 `py_compile`
- 只跑与数据处理页直接相关的窄测

## 完成判定

- `process_page` 的明确未用导入被清理。
- 没有引入新的运行时问题。
