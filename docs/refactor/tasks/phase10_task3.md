# Phase 10 Task 3

## 阶段

- Phase 10 / extension-runtime-and-api-hardening

## 对应方案

- `docs/refactor/12-phase-10-extension-runtime-and-api-hardening.md`

## 背景

- 当前 `core.extension_api` 仍是主要实现承载文件，未满足 `Phase 10` 的完成定义。
- `processing/data_engine.py` 仍接受旧式嵌套 `params["lines"]["lines_list"]` 协议，旧协议清理未闭环。
- `core.extension_loader.py`、`core.extension_invoker.py`、`processing/extension_tools.py` 仍存在 compatibility shell，需要明确其保留范围并避免继续承载主要实现。

## 目标

- 把扩展 contracts / registry / loader / runtime-invoker 从 `core.extension_api` 拆到独立模块。
- 将 `core.extension_api` 收口为受控 re-export / facade 层，而不是继续承载主要实现。
- 从处理 pipeline 主链路移除旧嵌套 `lines` 协议支持，并补齐拒绝路径窄测。
- 让 `core.extension_loader.py` 与 `core.extension_invoker.py` 改为转向新模块边界，而不是继续依赖 monolith。

## 本任务范围

- 新建 `core/extensions/*` 模块，承接：
  - contracts / types
  - registry
  - loader / report
  - runtime / invoker
- 调整 `core.extension_runtime.py`、`core.extension_loader.py`、`core.extension_api.py` 的实现归属。
- 调整 `processing/data_engine.py` 的多曲线参数解析，只接受顶层 `lines_list`。
- 增补与更新窄范围测试：
  - extension runtime / loader
  - protocol cleanup
  - processing pipeline
  - 相关架构 guardrails

## 不纳入

- 大曲线热路径优化
- 超大 UI 页面拆分
- UI 风格一致性整理
- 与扩展无关的业务状态重构

## 验证

- 以扩展 runtime、extension loader、protocol cleanup、processing pipeline、相关 UI smoke 的窄测为准。
- 不做全量回归测试。

## 提交计划

- `start`
  - 新模块边界落地，`core.extension_api` 开始降级为 facade。
- `checkpoint`
  - 旧协议主链路清理、runtime/loader 改接新模块、窄测通过。
- `end`
  - Phase 10 验收标准满足，compat 范围和保留项明确。

## 完成判定

- `core.extension_api` 不再是主要实现承载文件。
- `processing/data_engine.py` 不再接受旧嵌套 `lines` 协议。
- `core.extension_loader.py`、`core.extension_invoker.py` 只承担受控兼容导出。
- 相关窄测覆盖主链路与拒绝路径，并通过。
