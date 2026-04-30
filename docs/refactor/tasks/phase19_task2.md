# Phase 19 Task 2

## 阶段

- Phase 19 / expression-engine-and-processing-contract-normalization

## 对应方案

- `docs/refactor/23-phase-19-expression-engine-and-processing-contract-normalization.md`

## 目标

- 抽出共享表达式执行服务，收口 `data_engine`、`transform`、`pairwise_compute` 中重复的 `eval` 上下文与 numpy/标量回退逻辑。

## 本任务范围

- `core/expression_execution.py`
- `processing/data_engine.py`
- `extensions/processing/transform.py`
- `extensions/processing/pairwise_compute.py`
- `extensions/plot/plot_circle_annotation.py`
- `extensions/plot/plot_arrow_annotation.py`
- `extensions/plot/plot_text_annotation.py`
- `extensions/plot/plot_rectangle_annotation.py`
- `extensions/plot/plot_reference_line.py`
- `extensions/plot/plot_dual_curve_band.py`
- `extensions/plot/plot_polar_projection.py`
- `extensions/plot/plot_science_style.py`

## 不纳入

- 沙箱系统重写
- 新 DSL 设计
- 全量 lint / 全量回归测试

## 验证

- `./.venv/bin/python -m py_compile core/expression_execution.py processing/data_engine.py extensions/processing/transform.py extensions/processing/pairwise_compute.py extensions/plot/plot_circle_annotation.py extensions/plot/plot_arrow_annotation.py extensions/plot/plot_text_annotation.py extensions/plot/plot_rectangle_annotation.py extensions/plot/plot_reference_line.py extensions/plot/plot_dual_curve_band.py extensions/plot/plot_polar_projection.py extensions/plot/plot_science_style.py`
- `./.venv/bin/python -m unittest tests.test_extension_runtime.TestExtensionRuntime.test_request_builds_curve_buffers tests.test_backend.TestDataEngine.test_apply_pipeline_empty_ops`

## 完成判定

- 裸 `eval` 的共享执行入口已经落地，并被 `data_engine` 与相关扩展复用。
- `transform` / `pairwise_compute` / `data_engine` 的表达式契约明显收口，错误边界更一致。
