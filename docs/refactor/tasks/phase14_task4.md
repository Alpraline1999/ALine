# Phase 14 Task 4

## 阶段

- Phase 14 / redundancy-elimination-and-architectural-consistency

## 对应方案

- `docs/refactor/17-phase-14-redundancy-elimination-and-architectural-consistency.md`

## 目标

- 在明确 `DataPage` 不是共享扩展侧栏页面的前提下，整理其页面状态和壳层边界。
- 盘点并收敛重复的状态初始化，避免继续在单文件里堆积边界不清的逻辑。

## 本任务范围

- `ui/pages/data_page.py`
- `ui/page_view_state.py`
- 与 `DataPage` 直接耦合的少量支撑代码

## 不纳入

- DataPage 共享扩展侧栏接入
- 大规模拆文件
- 页面视觉重设计
- 业务流程重构

## 验证

- 先做 `py_compile`，再做 `data_page` / `global_extension_config` 的窄测。
- 不做全量回归测试。

## 完成判定

- `DataPage` 的职责边界与状态初始化更清晰。
- 文档与代码继续保持“不把它当作 extension-panel page”的一致前提。
