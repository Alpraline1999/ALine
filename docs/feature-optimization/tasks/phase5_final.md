# Phase 5 Final: ChartPage 大曲线异步渲染 + AnalysisPage 全部异步 + 进度反馈

1. ChartPage: 大曲线(>10000 点)重绘分两步 — 先 decimated 预览，再后台渲染
2. AnalysisPage: 全部异步 (移除 50000 阈值)，使用 BackgroundTask 带进度
3. 进度反馈: 状态栏显示 running/completed/failed text
