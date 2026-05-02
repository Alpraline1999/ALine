# Phase 15 Final: 分析结果曲线导出与输出线契约规范化

## 目标

收口分析页 `curve_fit`、`peak_detect` 等分析结果的输出线契约，恢复结果曲线导出能力，并避免当前 tab、已保存结果恢复和导出流程再次分叉。

## 实施

1. `ui/pages/analysis_page.py`
   - 让当前激活 tab 成为导出与按钮状态的优先数据源
   - 为 `curve_fit`、`error_compare`、`peak_detect` 提供输出线回退构造
   - 在结果视图渲染和 tab 切换后同步导出按钮状态
   - 将分析任务完成回调前移到任务启动前，避免快速任务漏掉结果回调
2. `core/task_runner.py`
   - 为 `TaskManager.run()` 增加启动前信号回调挂接能力
   - 保证分析任务的 finished / error 回调不会因竞态被错过
3. `tests/test_ui.py`
   - 增加曲线拟合导出窄测
   - 增加峰值检测导出窄测
   - 增加多 tab 切换后的当前结果导出窄测
   - 增加已保存分析结果恢复后导出窄测
4. `docs/feature-optimization/tasks/phase15_task1.md`
   - 记录本阶段任务拆分

## 验证

- `./.venv/bin/python -m pytest tests/test_ui.py -q -k 'curve_fit_result_can_export_series_with_export_plan or peak_detect_result_can_export_series_with_export_plan or export_result_series_uses_current_tab_result or saved_curve_fit_result_tab_can_export_series_after_restore or statistics_result_hides_export_curve_button_without_lines'`

## 结论

- `curve_fit` 结果曲线导出已恢复。
- `peak_detect` 的多输出线导出保持可用。
- 当前 tab 与已保存结果恢复后的导出契约已统一。
- 本阶段未做全量回归，仅保留窄测覆盖核心导出链路。

