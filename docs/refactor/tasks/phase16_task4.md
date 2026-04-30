# Phase 16 Task 4

## 阶段

- Phase 16 / static-quality-and-reliability-hardening

## 对应方案

- `docs/refactor/19-phase-16-static-quality-and-reliability-hardening.md`

## 目标

- 将 `digitize_page` 里一小组高频匿名回调替换为具名方法，开始收口 UI 回调硬化。

## 本任务范围

- `ui/pages/digitize_page.py`

## 不纳入

- 全部 lambda 一次性清理
- 页面级状态桥接重构
- 新业务功能

## 验证

- 聚焦 `digitize_page` 的 `py_compile`
- 只跑与自动识别和导出相关的窄测

## 完成判定

- 至少一组匿名回调被具名方法替代。
- 自动识别与导出范围行为保持不变。
