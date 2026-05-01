# Phase 32 Task 1：AI 命令层 series 查找逻辑下沉

## 目标

- 将 `ai/command_registry.py` 中共享的 series 解析逻辑抽离到独立 helper 模块。
- 让命令注册表更接近纯编排/路由，而不是继续维护具体查找策略。
- 用窄测锁定 exact/normalized/ambiguous series 解析行为。

## 任务拆分

1. 新建 `ai/command_series_lookup.py`，收纳 series 规范化、遍历和解析逻辑。
2. 让 `ai/command_registry.py` 复用该 helper，移除重复实现。
3. 为新的 helper 补一个窄测，验证精确匹配、规范化匹配和歧义返回。
4. 通过 `py_compile` 和命令层相关窄测验证这次拆分。
5. 使用 `important-change-commit` 形成 Phase 32 检查点提交。

## 验收方式

- `py_compile` 通过。
- 命令层窄测通过，且 series 解析结果与拆分前一致。
- 提交说明清楚描述职责下沉的边界和验证结果。
