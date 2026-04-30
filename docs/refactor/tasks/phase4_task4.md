# Phase 4 Task 4

## 阶段

- Phase 4 / extension-runtime-and-global-assets

## 对应方案

- `docs/refactor/05-phase-4-extension-runtime-and-global-assets.md`

## 目标

- 将默认报告模板从分析实现中抽离。
- 让 `GlobalAssetCatalog` 只依赖独立资源模块。

## 本任务范围

- 新增 `core/report_templates.py`。
- 让 `core/global_assets.py` 不再导入 `core.analysis_engine` 的默认模板常量。
- 让报告模板对话框与分析页改用独立资源模块。

## 验证

- `python3 -m unittest tests.test_report_templates tests.test_refactor_guardrails`
- `python3 -m py_compile core/report_templates.py core/global_assets.py core/analysis_engine.py ui/pages/analysis_page.py ui/dialogs/report_template_dialog.py tests/test_report_templates.py`

## 完成判定

- `GlobalAssetCatalog` 不再依赖分析实现细节。
- 默认报告模板成为独立共享资源。
