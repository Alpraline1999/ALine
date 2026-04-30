# Phase 4 Task 1

## 阶段

- Phase 4 / extension-runtime-and-global-assets

## 对应方案

- `docs/refactor/05-phase-4-extension-runtime-and-global-assets.md`

## 目标

- 把 builtin 扩展注册从页面构造器中移出。
- 通过统一 bootstrap 触发 builtin 扩展加载。

## 本任务范围

- 新增统一的扩展 bootstrap 入口。
- 让 `AppContext` 在创建扩展 runtime 时完成 builtin 扩展注册。
- 删除 `AnalysisPage` 与 `DigitizePage` 中的页面内注册调用。

## 验证

- `python3 -m unittest tests.test_extension_bootstrap tests.test_refactor_guardrails`
- `python3 -m py_compile core/extension_bootstrap.py app/context.py ui/pages/analysis_page.py ui/pages/digitize_page.py tests/test_extension_bootstrap.py`

## 完成判定

- 页面构造路径不再自行注册 builtin 扩展。
- builtin 扩展加载由统一 bootstrap 入口承担。
