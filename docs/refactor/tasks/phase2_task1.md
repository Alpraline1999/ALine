# Phase 2 Task 1

## 阶段

- Phase 2 / project-session-and-domain-services

## 对应方案

- `docs/refactor/03-phase-2-project-session-and-domain-services.md`

## 目标

- 落地 `ProjectRepository` 与 `ProjectMigrationService` 的首个可用切片。
- 先把 `ProjectManager` 的项目打开、保存与版本迁移职责抽出为独立服务。

## 本任务范围

- 新增 `ProjectRepository`。
- 新增 `ProjectMigrationService`。
- 让 `ProjectManager` 通过新服务执行：
  - 项目打开
  - 项目保存
  - v0.2 / v0.3 迁移
  - 新项目树初始化
- 补对应窄测。

## 验证

- `python3 -m unittest tests.test_project_repository tests.test_project_migration_service tests.test_refactor_guardrails`
- `python3 -m py_compile core/project_repository.py core/project_migration_service.py core/project_manager.py tests/test_project_repository.py tests/test_project_migration_service.py`

## 完成判定

- `ProjectManager` 不再直接承载项目打开、保存和版本迁移的核心实现。
- 新服务在不改变现有行为的前提下提供独立调用面。
