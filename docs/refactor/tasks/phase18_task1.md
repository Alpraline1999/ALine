# Phase 18 Task 1

## 阶段

- Phase 18 / shared-processing-foundation-and-dependency-direction-repair

## 对应方案

- `docs/refactor/22-phase-18-shared-processing-foundation-and-dependency-direction-repair.md`

## 目标

- 先完成低风险一致性收口、扩展类型边界修复，并统一 `process_page` 的 matplotlib bootstrap 入口。

## 本任务范围

- `core/extension_api.py`
- `core/extension_runtime.py`
- `core/extension_types.py`
- `ai/skill_runner.py`
- `core/project_manager.py`
- `ui/pages/data_page.py`
- `ui/pages/process_page.py`

## 不纳入

- 表达式引擎重写
- 扩展协议大版本调整
- 共享 line helper 抽取
- 全量 lint / 全量回归测试

## 验证

- `./.venv/bin/python -m py_compile core/extension_api.py core/extension_runtime.py core/extension_types.py ai/skill_runner.py core/project_manager.py ui/pages/data_page.py ui/pages/process_page.py`
- `./.venv/bin/python -m unittest tests.test_extension_runtime.TestExtensionRuntime.test_request_builds_curve_buffers tests.test_backend.TestDataEngine.test_apply_pipeline_empty_ops`

## 完成判定

- `extension_api.py` 中确认未使用的分析归一化函数已移除，且 plot 类型边界已迁到独立模块。
- `skill_runner.py`、`project_manager.py`、`data_page.py` 中的低风险噪声已清理。
- `process_page.py` 的 matplotlib bootstrap 与其他页面支持模块一致。
