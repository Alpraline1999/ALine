# Phase 20 Task 1

## 阶段

- Phase 20 / project-session-and-command-orchestration-decomposition

## 对应方案

- `docs/refactor/24-phase-20-project-session-and-command-orchestration-decomposition.md`

## 目标

- 先提炼 `ProjectManager` 的稳定服务边界，优先把项目树与资产管理职责从单文件编排中心中切出来。

## 本任务范围

- `core/project_manager.py`
- 新的 `core/project_services.py` 或等价服务模块
- 直接依赖 `ProjectManager` 的少量 glue

## 不纳入

- 全面重构 `ai/command_layer.py`
- 项目文件格式重写
- `MainWindow` 全面重构
- 全量回归测试

## 验证

- `./.venv/bin/python -m py_compile core/project_manager.py core/project_services.py`
- 命中的 project/session 窄测

## 完成判定

- 至少一组稳定的 project service 边界从 `ProjectManager` 中分离出来。
- `ProjectManager` 对已提炼职责开始转为受控调用，而不是继续内联增长。
