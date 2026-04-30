# Phase 10 Task 2

## 阶段

- Phase 10 / extension-runtime-and-api-hardening

## 对应方案

- `docs/refactor/12-phase-10-extension-runtime-and-api-hardening.md`

## 目标

- 清理扩展系统中的旧协议支持。
- 继续收口 `core.extension_api` 中残留的兼容分支，并让运行时契约更接近正式形态。

## 本任务范围

- 移除扩展配置中的旧式 `default_options["lines"]` 嵌套协议支持。
- 移除曲线/扩展参数中的老旧哨兵值兼容分支。
- 补充窄范围测试，确认旧协议入口已被拒绝。

## 验证

- 以窄范围单元测试和 `py_compile` 为准。
- 不做全量回归测试。

## 完成判定

- 旧协议分支已从主路径中清理。
- 相关测试明确验证旧协议已不再被接受。
- 未引入新的兼容回退分支。
