# Phase 8 Task 1: AnalysisResult 来源追溯字段

## 目标

提升分析结果的追溯性: 记录每份结果来自哪组输入、参数和模板。

## 实施

1. `models/schemas.py` 的 AnalysisResult 添加:
   - `input_snapshots: list[dict]` — 输入数据快照（名称、来源路径等）
   - `template_snapshot: dict` — 报告模板快照
2. `analysis_page.py` _save_result 在创建 AnalysisResult 时填入追溯信息
