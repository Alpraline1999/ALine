# Phase 25 Task 1

## 阶段

- Phase 25 / extension-tests-and-module-surface-normalization

## 对应方案

- `docs/refactor/30-phase-25-extension-tests-and-module-surface-normalization.md`

## 目标

- 收口扩展测试契约、包入口导出面和低风险命名分裂。

## 本任务范围

- `ui/dialogs/__init__.py`
- `ui/widgets/__init__.py`
- `ui/pages/analysis_page_support.py`
- `ui/pages/process_page.py`
- `ui/pages/analysis_page.py`
- `tests/test_page_support_modules.py`

## 不纳入

- 业务流程重写
- 项目树深拆
- 新 UI 视觉改版

## 验证

- `./.venv/bin/python -m py_compile ui/dialogs/__init__.py ui/widgets/__init__.py ui/pages/analysis_page_support.py ui/pages/process_page.py ui/pages/analysis_page.py tests/test_page_support_modules.py`
- `./.venv/bin/python -m unittest tests.test_page_support_modules`

## 完成判定

- 包入口提供稳定导出面。
- `_HAS_MPL` / `HAS_MATPLOTLIB` 命名分裂收口或明确标记为唯一约定。
