# Phase 5 Task 6

## 阶段

- Phase 5 / cleanup-file-splitting-and-dead-path-removal

## 对应方案

- `docs/refactor/06-phase-5-cleanup-file-splitting-and-dead-path-removal.md`

## 目标

- 将 `ui/pages/digitize_page.py` 的基础常量与输入对话框工具类抽出为支持模块。
- 让数字化页主体更聚焦于采点、校准和导出交互。

## 本任务范围

- 新增 `ui/pages/digitize_page_support.py`。
- 将数字化页顶部的支持常量与 `_InputDialog` 迁出。
- 保持数字化页现有行为不变。

## 验证

- `python3 -m unittest tests.test_refactor_guardrails`
- `python3 -m py_compile ui/pages/digitize_page.py ui/pages/digitize_page_support.py`

## 完成判定

- 数字化页基础支持层与页面主体完成分离。
