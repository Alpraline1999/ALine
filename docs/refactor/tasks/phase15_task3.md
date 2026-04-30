# Phase 15 Task 3

## 阶段

- Phase 15 / monolith-decomposition-and-shared-widget-extraction

## 对应方案

- `docs/refactor/18-phase-15-monolith-decomposition-and-shared-widget-extraction.md`

## 目标

- 收口 `analysis_page` 的 `workspace_state` 代理属性，验证页面状态桥接模式可以替代一部分直接代理堆积。

## 本任务范围

- `ui/pages/analysis_page.py`
- 必要时补充与之配套的最小桥接支撑

## 不纳入

- `chart_page` / `process_page` / `digitize_page` 的全面代理重构
- 新业务功能
- UI 视觉重设计

## 验证

- 先做 `py_compile`，再做分析页相关窄测。
- 不做全量回归测试。

## 完成判定

- `analysis_page` 的一组直接 `workspace_state` 代理属性被收口。
- 页面状态边界更清晰，且没有引入行为变化。
