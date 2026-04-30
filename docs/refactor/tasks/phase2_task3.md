# Phase 2 Task 3

## 阶段

- Phase 2 / project-session-and-domain-services

## 对应方案

- `docs/refactor/03-phase-2-project-session-and-domain-services.md`

## 目标

- 建立 `ProjectSession` 作为显式项目运行时入口。
- 先让 `AppContext` 和 `ProjectManager` 都围绕 `ProjectSession` 收敛，不提前迁页面业务状态。

## 本任务范围

- 新增 `ProjectSession` 运行时对象。
- 让 `ProjectManager` 暴露并使用 `ProjectSession`。
- 让 `AppContext` 的默认 `project_session` 指向正式的 `ProjectSession` 实例，而不是直接回退到 `ProjectManager`。
- 补对应窄测。

## 验证

- `python3 -m unittest tests.test_project_session tests.test_app_runtime tests.test_refactor_guardrails`
- `python3 -m py_compile core/project_session.py core/project_manager.py app/context.py tests/test_project_session.py tests/test_app_runtime.py`

## 完成判定

- 代码库中已经存在正式的 `ProjectSession` 运行时对象。
- `AppContext.project_session` 默认不再直接指向 `ProjectManager` 本体。
