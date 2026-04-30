# Phase 18 Task 2

## 阶段

- Phase 18 / shared-processing-foundation-and-dependency-direction-repair

## 对应方案

- `docs/refactor/22-phase-18-shared-processing-foundation-and-dependency-direction-repair.md`

## 目标

- 把对齐、插值、排序去重、采样间距和基础平滑算法收口到中性共享层。

## 本任务范围

- `core/line_tools.py`
- `processing/data_engine.py`
- `extensions/processing/extension_tools.py`
- `extensions/processing/resample.py`
- `extensions/processing/smooth.py`
- `processing/smoother.py`

## 不纳入

- 扩展协议大版本调整
- 表达式引擎重写
- UI 页面继续拆分
- 全量 lint / 全量回归测试

## 验证

- `./.venv/bin/python -m py_compile core/line_tools.py processing/data_engine.py extensions/processing/extension_tools.py extensions/processing/resample.py extensions/processing/smooth.py processing/smoother.py`
- `./.venv/bin/python -m unittest tests.test_extension_runtime.TestExtensionRuntime.test_request_builds_curve_buffers tests.test_backend.TestDataEngine.test_apply_pipeline_empty_ops`

## 完成判定

- `processing/data_engine.py` 不再直接依赖 `extensions.processing.extension_tools` 的稳定基础 helper。
- `extensions/processing/resample.py` 不再维护本地 `_sorted_unique_xy` / `_interp_linear` 重复实现。
- `extensions/processing/smooth.py` 直接复用 `processing.smoother` 的平滑算法。
