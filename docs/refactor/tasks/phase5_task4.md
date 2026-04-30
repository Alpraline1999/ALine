# Phase 5 Task 4

## 阶段

- Phase 5 / cleanup-file-splitting-and-dead-path-removal

## 对应方案

- `docs/refactor/06-phase-5-cleanup-file-splitting-and-dead-path-removal.md`

## 目标

- 将 `ui/pages/data_page.py` 的前置支持层抽出为独立模块。
- 让数据页主体更聚焦于交互流程和业务动作，而不是基础常量与辅助视图类。

## 本任务范围

- 新增 `ui/pages/data_page_support.py`。
- 将数据页顶部的常量、状态 dataclass、轻量 helper 类与 matplotlib 初始化迁出。
- 保持数据页现有行为不变。

## 验证

- `python3 -m unittest tests.test_refactor_guardrails`
- `python3 -m py_compile ui/pages/data_page.py ui/pages/data_page_support.py`

## 完成判定

- 数据页主体与其前置支持层完成分离。
