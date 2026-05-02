# Phase 5 Final: ChartPage 大曲线异步渲染 + AnalysisPage 全部异步 + 进度反馈

## 目标

把大输入与长耗时绘制从同步阻塞改为渐进反馈，减少 UI 卡顿。

## 实施

1. `ui/pages/chart_page.py`
   - 大曲线(>10000 点)先显示 decimated 预览
   - 后续补充完整渲染阶段与过期结果保护
2. `ui/pages/analysis_page.py`
   - 去掉固定阈值分支，分析任务统一走 BackgroundTask
   - 进度回调更新状态栏
3. `core/task_runner.py`
   - 保持跨页面共享任务壳层语义稳定
