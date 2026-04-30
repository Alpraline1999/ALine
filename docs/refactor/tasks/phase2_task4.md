# Phase 2 Task 4

## 阶段

- Phase 2 / project-session-and-domain-services

## 对应方案

- `docs/refactor/03-phase-2-project-session-and-domain-services.md`

## 目标

- 让 `DataFile + DataSeries` 成为正式运行时写入主链路。
- 把 `Dataset` 降级为兼容镜像，避免继续双轨写入。

## 本任务范围

- 调整 `sync_legacy_datasets`，让 `datasets` 明确成为 `data_files` 的兼容镜像。
- 让旧的 dataset 相关管理方法改为通过 `DataFile` 主链路执行。
- 调整至少一条仍直接依赖 `datasets` 的运行时主链路为 `data_files` 优先。
- 补对应窄测。

## 验证

- `python3 -m unittest tests.test_project_dataset_runtime_bridge tests.test_refactor_guardrails`
- `python3 -m py_compile core/project_manager.py core/project_asset_service.py models/schemas.py ui/pages/process_page.py tests/test_project_dataset_runtime_bridge.py`

## 完成判定

- 新的正式写路径不再直接写入 `Dataset`。
- `datasets` 只作为兼容镜像保留，不再是正式运行时容器。
