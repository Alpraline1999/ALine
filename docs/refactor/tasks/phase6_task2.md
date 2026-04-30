# Phase 6 Task 2

## 阶段

- Phase 6 / quality-gates-and-test-restructure

## 对应方案

- `docs/refactor/07-phase-6-quality-gates-and-test-restructure.md`

## 目标

- 拆分模块级窄测与关键集成测试。
- 让新拆出的 support 模块拥有各自的最小验证文件。

## 本任务范围

- 新增 support 模块的窄测。
- 新增页面/主窗口的最小集成 smoke 测试。
- 保持原有大测试文件可继续运行，但不再承担全部职责。

## 验证

- `./.venv/bin/python -m unittest tests.test_refactor_guardrails tests.test_page_support_modules tests.test_ui_smoke`
- `./.venv/bin/python -m py_compile tests/test_page_support_modules.py tests/test_ui_smoke.py`

## 完成判定

- 模块级窄测与关键集成 smoke test 完成分层。
