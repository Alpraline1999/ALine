# Phase 16 Task 5

## 阶段

- Phase 16 / static-quality-and-reliability-hardening

## 对应方案

- `docs/refactor/19-phase-16-static-quality-and-reliability-hardening.md`

## 目标

- 收口 `process_page` 中一组可预期的宽异常捕获，把输入解析失败和真正的运行时异常区分开。

## 本任务范围

- `ui/pages/process_page.py`

## 不纳入

- import-time 的 matplotlib 兜底
- 整体异常策略重写
- 业务流程修改

## 验证

- 聚焦 `process_page` 的 `py_compile`
- 只跑与处理页直接相关的窄测

## 完成判定

- 一组可预期的异常捕获被缩窄到具体错误类型。
- 行为保持稳定。
