# Phase 5 Task 1: 大曲线异步化 — 文档与最小接缝

Phase 5 要求为大曲线任务建立后台执行框架。由于涉及 process_page / analysis_page 等遗留 monolith，最小安全改动：

1. 在 `core/extension_types.py` 添加 `TaskProgress` 数据类 (轻量、可复用)
2. 其余异步改造转入功能优化后续阶段，随 legacy monolith 拆分推进
