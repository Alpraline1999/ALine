# Phase 5 Task 5

## 阶段

- Phase 5 / cleanup-file-splitting-and-dead-path-removal

## 对应方案

- `docs/refactor/06-phase-5-cleanup-file-splitting-and-dead-path-removal.md`

## 目标

- 将 `ui/pages/chart_page.py` 的基础曲线/绘图支持层抽出为独立模块。
- 让图表页主体聚焦于页面交互和图表工作集流程。

## 本任务范围

- 新增 `ui/pages/chart_page_support.py`。
- 将图表页顶部的样式常量与内建 extension 定义迁出。
- 保持图表页现有行为不变。

## 验证

- `python3 -m unittest tests.test_refactor_guardrails`
- `python3 -m py_compile ui/pages/chart_page.py ui/pages/chart_page_support.py`

## 完成判定

- 图表页基础样式支持层与页面主体完成分离。
