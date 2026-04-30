# Phase 4 Task 3

## 阶段

- Phase 4 / extension-runtime-and-global-assets

## 对应方案

- `docs/refactor/05-phase-4-extension-runtime-and-global-assets.md`

## 目标

- 继续拆分 `extension_api.py` 的职责边界。
- 把 loader / invoker 的公开入口迁移到独立模块。

## 本任务范围

- 新增 `core/extension_loader.py` 与 `core/extension_invoker.py`。
- 将页面和核心模块的加载 / 调用入口切换到新模块。
- 保留 `extension_api.py` 兼容入口，但不再作为新代码的首选导入点。

## 验证

- `python3 -m unittest tests.test_extension_bootstrap tests.test_line_tools tests.test_refactor_guardrails`
- `python3 -m py_compile core/extension_loader.py core/extension_invoker.py ui/pages/chart_page.py ui/pages/digitize_page.py ui/pages/analysis_page.py core/analysis_engine.py ui/pages/home_page.py ui/pages/process_page.py ui/pages/settings_page.py ui/widgets/extension_panel.py`

## 完成判定

- loader / invoker 的新分层模块可被页面和 core 直接使用。
- `extension_api.py` 不再承担 loader / invoker 的新调用入口职责。
