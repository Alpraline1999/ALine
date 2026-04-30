# Phase 5 Task 7

## 阶段

- Phase 5 / cleanup-file-splitting-and-dead-path-removal

## 对应方案

- `docs/refactor/06-phase-5-cleanup-file-splitting-and-dead-path-removal.md`

## 目标

- 将 `ui/pages/analysis_page.py` 的前置支持层抽出为独立模块。
- 让分析页主体更聚焦于分析工作流和报告输出。

## 本任务范围

- 新增 `ui/pages/analysis_page_support.py`。
- 将分析页顶部的支持常量、matplotlib 初始化与轻量结果表控件迁出。
- 保持分析页现有行为不变。

## 验证

- `python3 -m unittest tests.test_refactor_guardrails`
- `python3 -m py_compile ui/pages/analysis_page.py ui/pages/analysis_page_support.py`

## 完成判定

- 分析页支持层与页面主体完成分离。
