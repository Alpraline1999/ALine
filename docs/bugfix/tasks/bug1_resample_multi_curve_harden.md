# Bug 1 Task: 重采样后多曲线扩展仍然报错需要重采样

## 问题描述

在 Pipeline 中对多条曲线执行重采样操作后，再添加多曲线均值或双曲线运算扩展时，仍然报错：
```
ValueError: 输入曲线 X 坐标未对齐，需进行坐标间距重采样
```

## 触发场景

AsyncPipelineRunner 将 pipeline ops 逐个传递给 `apply_pipeline_to_lines()`。
当 pipeline 包含 `[resample, multi_curve_mean]` 时：

1. **Step 0**: `apply_pipeline_to_lines(lines, [resample], selected_lines=pool)` → 重采样正确，曲线对齐 ✓
2. **Step 1**: `apply_pipeline_to_lines(result, [multi_curve_mean], selected_lines=pool)`
   - `_resolve_pairing_inputs(multi_curve_mean_op, pool)` 从**原始 pool** 读取曲线
   - 拿到的是**未重采样**的原始曲线！不是 step 0 的输出
   - `multi_curve_mean_handler` 收到未对齐曲线 → `align_lines_to_common_x(lines, {"align_mode": "strict"})` → **抛出 ValueError**

## 根因

`processing/async_runner.py:_PipelineWorker.run()` 第 93-105 行：
```python
for i, op in enumerate(self._ops):
    result, step_warnings = apply_pipeline_to_lines(
        result,
        [op],                          # ← 每次只传一个 op
        selected_lines=self._selected_lines,  # ← 总是用原始 pool
    )
```

逐步骤执行时，pairing op 的 `_resolve_pairing_inputs` 从 `selected_lines`（原始 pool）读取输入曲线，
**不感知**前序步骤（重采样）的输出结果。

同步路径 `_build_output_series_batch` 没有此问题（一次性传递所有 ops）。

## 修复

**文件**: `processing/async_runner.py`
**修改**: 在 `run()` 方法中检测 pipeline 是否包含 pairing op（多曲线扩展）：
- 如果包含：一次性传递所有 ops 给 `apply_pipeline_to_lines`
- 如果不包含：继续逐步骤执行（兼容进度报告）

## 验收标准

- [ ] 异步 Pipeline 中 resample + multi_curve_mean 能正常执行
- [ ] 异步 Pipeline 中 resample + pairwise_compute 能正常执行
- [ ] 单一 op 的 Pipeline 仍然逐步骤执行（进度报告正常）
- [ ] backend 回归全部通过
