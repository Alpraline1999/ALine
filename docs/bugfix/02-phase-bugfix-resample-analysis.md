# Bugfix Phase: 重采样/多曲线扩展与分析扩展 bool 迭代错误

## 目标与完成定义

修复两个运行时 bug：
1. Pipeline 中先重采样再多曲线处理，仍然报错"输入曲线 X 坐标未对齐，需进行坐标间距重采样"
2. 所有分析扩展运行时报错 `TypeError: 'bool' object is not iterable`

**完成定义：**
- Pipeline 中 resample + multi_curve_mean/pairwise_compute 能正常执行
- 所有分析扩展（内置 + 自定义）不再抛出 "bool object is not iterable"
- backend 回归测试全部通过
- 不引入新失败

## 问题清单

| # | 问题 | 根因（真实） | 涉及文件 |
|---|------|-------------|---------|
| 1 | Pipeline 中重采样后多曲线扩展仍报 X 未对齐 | **`AsyncPipelineWorker.run()` 逐步骤执行 ops**：每次只传单个 op 给 `apply_pipeline_to_lines`。pairing op 的 `_resolve_pairing_inputs` 从原始 `selected_lines` pool 读取输入曲线，**不感知**前序重采样步骤的输出 | `processing/async_runner.py`（主因）、`processing/data_engine.py` |
| 2 | 所有分析扩展报 "bool object is not iterable" | 多个入口未防护 bool：`normalize_lines()`/`normalize_line()` 的 `raw in (None, "", [], ())` 未拦截 True；`series_payloads_to_curve_batch()` 未防护 bool；**分析页/分析引擎**中大量 `list(result.get("X") or [])` 模式在 result 中某键值为 True 时触发 `list(True)` | `core/line_tools.py`、`core/curve_data.py`、`core/extension_definition.py`（`normalize_extension_lines_list`）、`ui/pages/analysis_page.py`（`_normalize_analysis_output` 等）、`core/analysis_engine.py`（`run_analysis`）|

## 根因分析

### Bug 1：重采样后多曲线扩展仍报错

**真实的代码路径：**
1. 用户从处理页选择多条曲线 → 添加 `[resample, multi_curve_mean]` Pipeline → 点击运行
2. `AsyncPipelineWorker.run()` 启动异步执行（`async_runner.py:80`）
3. **逐个执行 ops**（`async_runner.py:93-105`）：
   ```
   for i, op in enumerate(self._ops):
       result, step_warnings = apply_pipeline_to_lines(
           result,         ← 逐步累积结果
           [op],           ← 每次只传一个 op
           selected_lines=self._selected_lines,  ← 始终使用原始 pool
       )
   ```
4. **Step 0** (resample)：`apply_pipeline_to_lines(lines, [resample], pool)` → 重采样正确 ✓
5. **Step 1** (multi_curve_mean)：`apply_pipeline_to_lines(resampled_lines, [multi_curve_mean], pool)`
   - `_find_single_pairing_op([multi_curve_mean])` → 返回 `(0, multi_curve_mean_op)`
   - `_resolve_pairing_inputs(multi_curve_mean_op, pool)` → 从**原始 pool**（`selected_lines`）读取曲线！
     → 拿到的是**未重采样**的原始曲线
   - `_execute_pairing_op(multi_curve_mean_op, pre)` → multi_curve_mean_handler 收到未对齐曲线
   - `align_lines_to_common_x(input_lines, {"align_mode": "strict"})` → **抛出 ValueError**

**同步路径** `_build_output_series_batch` 一次性传递所有 ops，无此问题。

**修复：** 在 async_runner 中检测 pairing op，存在时一次性传递所有 ops。

### Bug 2：bool object is not iterable

**真实的触发路径是多个未防护入口的任意组合：**

1. **`normalize_extension_lines_list()`**（`extension_definition.py:232`）：
   ```python
   if raw in (None, "", False):  # True in (None, "", False) → False！
   ```
   `True` 通过检查，`int(True)` → `1`，被静默转换为有效行下标。

2. **结果展示层的 `list(result.get("X") or [])` 模式**：
   ```python
   list(result.get("lines") or [])          # result["lines"]=True → list(True)
   list(r.get("_plot_series", []) or [])    # result["_plot_series"]=True → list(True)
   list(result.get("params", []) or [])     # result["params"]=True → list(True)
   list(result.get("peaks", []) or [])      # result["peaks"]=True → list(True)
   ```
   当 result dict 中这些键的值为 True/False 时，`or` 短路返回 True → `list(True)` 崩溃。

3. **`normalize_lines()`/`normalize_line()` 中的 `raw in` 模式**：
   ```python
   if raw in (None, "", [], ()):  # True in (...) → False
   ```

4. **`series_payloads_to_curve_batch()` 未防护 bool**
   ```python
   return [series_payload_to_curve_buffer(item) for item in raw]  # raw=True 崩溃
   ```

## 修复清单

### Bug 1

| 文件 | 修改 |
|------|------|
| `processing/async_runner.py` | `run()` 方法检测 pairing op：有则一次性传递所有 ops；无则继续逐步骤执行 |

### Bug 2

| 文件 | 修改 |
|------|------|
| `core/line_tools.py` | `normalize_line()`/`normalize_lines()` 增加 `isinstance(raw, bool)` → `[]` |
| `core/curve_data.py` | `series_payloads_to_curve_batch()` 增加 `isinstance(raw, bool)` → `[]` |
| `core/extension_definition.py` | `normalize_extension_lines_list()` 将 `raw in (None, "", False)` 改为 `raw is None or raw == "" or raw is False or raw is True` |
| `core/extension_runtime.py` | `invoke_analysis_extension_handler()`: `[dict(item or {}) for item in inputs]` → `[dict(item) for item in inputs if isinstance(item, dict)]` |
| `core/analysis_engine.py` | 新增 `_ensure_list()` 辅助函数；`run_analysis()` 中 `list(item.get("x", []) or [])` 改用 `_ensure_list`；`_build_curve_fit_analysis_result`/`peak_detect` 中 `list(result.get(...) or [])` 改用 `_ensure_list`；`_analysis_extension_report_placeholders` 中 `list(getattr(...) or [])` 改用 `_ensure_list` |
| `ui/pages/analysis_page.py` | 新增模块级 `_ensure_list()` 辅助函数；修复 `_normalized_table_sections`、`_normalized_text_sections`、`_normalize_analysis_output`、`_analysis_result_lines`、`_populate_detail_summary_view`、`_render_summary_view`、`_draw_result`、`_render_analysis_plot_from_result`、`_params_table` 等函数中所有 `list(... or [])` 模式 |

## 验收标准

- [ ] 异步 Pipeline 中 resample + multi_curve_mean 能正常执行
- [ ] 异步 Pipeline 中 resample + pairwise_compute 能正常执行
- [ ] backend 回归测试全部通过（265+ tests）
- [ ] `normalize_extension_lines_list(True)` 返回 `[]`
- [ ] `_ensure_list(True)` 返回 `[]`
- [ ] `normalize_lines(True)` 返回 `[]`
