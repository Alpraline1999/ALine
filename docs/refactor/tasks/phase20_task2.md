# Phase 20 Task 2

## 阶段

- Phase 20 / project-session-and-command-orchestration-decomposition

## 对应方案

- `docs/refactor/24-phase-20-project-session-and-command-orchestration-decomposition.md`

## 目标

- 把 `ai/command_layer.py` 中的命令定义、handler 和 registry 抽出，保留 dispatcher 只负责装配与路由。

## 本任务范围

- `ai/command_layer.py`
- 新的 `ai/command_registry.py` 或等价命令模块
- 少量直接依赖命令层的 glue

## 不纳入

- 新 AI 产品能力
- 命令语义破坏性变更
- `MainWindow` 全面重构

## 验证

- `./.venv/bin/python -m py_compile ai/command_layer.py ai/command_registry.py`
- 命中的 AI command / backend 窄测

## 完成判定

- dispatcher 不再承载大量具体命令实现。
- 命令定义、处理与注册有更清晰的归属边界。
