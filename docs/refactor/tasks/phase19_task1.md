# Phase 19 Task 1

## 阶段

- Phase 19 / expression-engine-and-processing-contract-normalization

## 对应方案

- `docs/refactor/23-phase-19-expression-engine-and-processing-contract-normalization.md`

## 目标

- 先把跨分析、处理、绘图扩展重复出现的 `_as_float` 类参数解析 helper 收口到共享入口。

## 本任务范围

- `core/value_parsing.py`
- `extensions/analysis/spectrum_analysis.py`
- `extensions/processing/kalman_filter.py`
- `extensions/plot/plot_circle_annotation.py`
- `extensions/plot/plot_arrow_annotation.py`
- `extensions/plot/plot_text_annotation.py`
- `extensions/plot/plot_rectangle_annotation.py`
- `extensions/plot/plot_reference_line.py`
- `extensions/plot/plot_dual_curve_band.py`
- `extensions/plot/plot_polar_projection.py`
- `extensions/plot/plot_science_style.py`

## 不纳入

- 裸 `eval` 表达式执行收口
- 沙箱系统重写
- UI 改版
- 全量 lint / 全量回归测试

## 验证

- `./.venv/bin/python -m py_compile core/value_parsing.py extensions/analysis/spectrum_analysis.py extensions/processing/kalman_filter.py extensions/plot/plot_circle_annotation.py extensions/plot/plot_arrow_annotation.py extensions/plot/plot_text_annotation.py extensions/plot/plot_rectangle_annotation.py extensions/plot/plot_reference_line.py extensions/plot/plot_dual_curve_band.py extensions/plot/plot_polar_projection.py extensions/plot/plot_science_style.py`
- `./.venv/bin/python -m unittest tests.test_extension_runtime.TestExtensionRuntime.test_request_builds_curve_buffers tests.test_backend.TestDataEngine.test_apply_pipeline_empty_ops`

## 完成判定

- 重复的 `_as_float` helper 不再在多个扩展文件中继续横向复制。
- `core/value_parsing.py` 成为共享数值解析入口。
