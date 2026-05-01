# Phase 5 Task 1: 统一后台任务壳层 + ProcessPage 集成

## 目标

建立跨页面共享的后台任务模型，避免大输入下 UI 阻塞。

## 实施

1. 创建 `core/task_runner.py`:
   - `BackgroundTask` — QObject，通过信号报告进度/结果
   - 支持 task_id, status, progress_text, progress_percent, cancel
   - 过期结果保护：旧 job_id 的结果不会覆盖新状态
2. 接入 `process_page.py`:
   - `_run_pipeline_now()` 使用 BackgroundTask 运行
   - 进度更新: UI 显示 "正在处理 N/M 个输入"
   - 取消支持: 重新运行时自动取消旧任务
   - 显示进度标签
