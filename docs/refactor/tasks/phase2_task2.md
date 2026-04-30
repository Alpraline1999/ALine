# Phase 2 Task 2

## 阶段

- Phase 2 / project-session-and-domain-services

## 对应方案

- `docs/refactor/03-phase-2-project-session-and-domain-services.md`

## 目标

- 落地 `ProjectTreeService` 与 `ProjectAssetService` 的首个可用切片。
- 先把共享树和项目级核心资产 CRUD 从 `ProjectManager` 中抽出。

## 本任务范围

- 新增 `ProjectTreeService`。
- 新增 `ProjectAssetService`。
- 让 `ProjectManager` 通过新服务执行：
  - 文件夹新增、节点重命名、节点删除、节点移动、空文件夹清理
  - `DataFile` 新增
  - `DataSeries` 重命名、删除、跨 `DataFile` 移动、追加
  - `Curve` 重命名、删除、跨 `ImageWork` 移动
- 补对应窄测。

## 验证

- `python3 -m unittest tests.test_project_tree_service tests.test_project_asset_service tests.test_refactor_guardrails`
- `python3 -m py_compile core/project_tree_service.py core/project_asset_service.py core/project_manager.py tests/test_project_tree_service.py tests/test_project_asset_service.py`

## 完成判定

- `ProjectManager` 不再直接承载上述树结构和项目级资产 CRUD 的核心实现。
- 新服务在不改变现有行为的前提下提供独立调用面。
