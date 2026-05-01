# Phase 9 Task 1: AI 模块启动链路解耦

## 目标

旧 AI 模块从启动链路和用户主流程中解耦：
- MainWindow 不应因 AI 模块导入失败而无法启动
- 隐藏未完成的 AI 入口

## 修改范围

检查 `main.py` / `main_window.py` 对 AI 模块的启动期导入路径，确保：
- AI 模块只在被显式调用时导入，不在模块级别 import
