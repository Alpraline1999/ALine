# Phase 16 Task 3

## 阶段

- Phase 16 / static-quality-and-reliability-hardening

## 对应方案

- `docs/refactor/19-phase-16-static-quality-and-reliability-hardening.md`

## 目标

- 收口 `chart_page` 当前暴露的未用导入噪声，继续推进 `F401` 类问题分批清理。

## 本任务范围

- `ui/pages/chart_page.py`

## 不纳入

- 图表渲染逻辑改写
- 大规模页面拆分
- 回调体系重构

## 验证

- 聚焦 `chart_page` 的 `py_compile`
- 只跑与图表页直接相关的窄测

## 完成判定

- `chart_page` 的明确未用导入被清理。
- 没有引入新的运行时问题。
