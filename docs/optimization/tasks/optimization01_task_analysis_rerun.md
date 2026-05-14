# Optimization 01 Task：分析页复跑使用结果配置

## 对应方案

- `docs/optimization/01-analysis-rerun-use-result-config.md`

## 目标

修改 `_rerun_current_analysis()`，使复跑时直接使用结果中保存的 `extension_options`，
而非从 UI 文本编辑器读取。

## 方案

1. 在 `_rerun_current_analysis()` 中，从 `view` 的 `params` 中提取 `extension_options`
2. 将 `_run_analysis()` 改为可选接受外部 `extension_options` 参数
3. 当有外部参数时，`_run_analysis()` 跳过 `_current_extension_analysis_options()` 调用的
   `_parse_extension_analysis_options_text()`，直接使用传入的参数
4. 普通"运行分析"不受影响

## 涉及文件

- `ui/pages/analysis_page.py`

## 验收

- 复跑使用结果保存的参数（通过直接传参）
- 普通运行仍从面板读取
