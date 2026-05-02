# Phase 11 Final: ChartPage 主题刷新路径切分 + 轻量渲染摘要

## 目标

让图表页的主题刷新不再直接走无差别完整重绘入口，并为大曲线保留预览阶段与轻量观测点。

## 实施

1. `ui/page_view_state.py`
   - 为 `ChartPageViewState` 增加待处理重绘原因与最近一次渲染摘要字段
2. `ui/pages/chart_page.py`
   - 区分 `theme` 与 `data` 两类重绘原因
   - 主题切换走 `_redraw("theme")` 调度入口，而不是直接触发完整重绘
   - 大曲线调度保留 decimated 预览，再延后完整渲染
   - 记录最近一次渲染的原因 / 模式 / 点数 / 耗时摘要
   - 将多处批量可见性、样式和模板/扩展应用入口切换到调度重绘路径
3. 新增 `tests/test_chart_page_phase11.py`
   - 覆盖隐藏页主题刷新挂起
   - 覆盖可见页主题刷新走 `theme` 调度
   - 覆盖大曲线预览调度
   - 覆盖渲染摘要状态

## 验证

- `./.venv/bin/python -m pytest tests/test_chart_page_phase11.py tests/test_ui_smoke.py -q`
