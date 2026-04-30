# Phase 4 Task 2

## 阶段

- Phase 4 / extension-runtime-and-global-assets

## 对应方案

- `docs/refactor/05-phase-4-extension-runtime-and-global-assets.md`

## 目标

- 将通用曲线/线工具迁入 `core`。
- 清除 `core -> extensions` 的直接导入依赖。

## 本任务范围

- 新增 `core/line_tools.py`。
- 让 `core/extension_api.py` 与 `core/analysis_engine.py` 直接依赖 `core/line_tools.py`。
- 收口架构守卫中的 core 依赖白名单。

## 验证

- `python3 -m unittest tests.test_line_tools tests.test_refactor_guardrails`
- `python3 -m py_compile core/line_tools.py core/extension_api.py core/analysis_engine.py tests/test_line_tools.py tests/test_refactor_guardrails.py`

## 完成判定

- `core/**` 中不再直接导入 `extensions.processing.extension_tools`。
- 线工具成为 `core` 的稳定基础设施。
