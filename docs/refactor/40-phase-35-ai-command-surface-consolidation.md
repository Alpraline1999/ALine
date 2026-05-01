# Phase 35：AI Command Surface Consolidation

## 目标与完成定义

目标：

- 消除 `ai.command_layer` 与 `ai.command_registry` 之间仍然存在的重复定义和单一中心化问题。
- 统一命令 schema、handler、动态工具目录、执行上下文和 agent 接入边界。
- 防止 AI 命令面再次同时承担“注册表 + 运行时 + 动态工具编排 + 全局资产接入”的多重职责。

完成定义：

- 命令定义只有一个可信来源，不再同时维护两套 `CommandResult` / `CommandDef` / `cmd_*` 实现。
- `CommandDispatcher` 只负责运行时分发，不再混合命令声明、动态工具目录构造和执行细节。
- 全局 prompt / skill / agent 动态工具入口有独立 provider / executor 边界。

## 进入前提

- `Phase 34` 已完成 `ProjectManager` 公共 façade 收口，AI 层可以依赖更稳定的项目查询/变更接口。
- 当前 AI agent 与命令调用链已有基本窄测基础。

## 本阶段纳入的范围

- `ai/command_layer.py`
- `ai/command_registry.py`
- `ai/agent.py`
- 与 AI 命令调用直接相关的 runtime / schema / dynamic tool provider 模块

## 本阶段不纳入的范围

- 新增 AI 功能
- 更换模型接入协议
- 扩展脚本执行沙箱的全新设计

## 本阶段禁止事项

- 禁止保留两套命令定义，仅靠导入顺序或转发维持兼容。
- 禁止把动态全局工具继续混入静态 command registry。
- 禁止在 dispatcher 中继续增加业务型 `cmd_*` 处理函数。

## 核心问题清单

- `ai.command_layer.py` 与 `ai.command_registry.py` 仍存在大量重复命令定义。
- `command_layer` 既导入 `command_registry`，又保留自身完整的 command handlers 和 schema，形成双源事实。
- 动态工具目录、全局 prompt/skill/agent 执行、OpenAI tools schema 生成仍集中在单一文件。

## 实施顺序

1. 明确唯一命令定义源：
   - registry-first，或
   - handlers-first + schema provider
2. 将动态工具目录提取为独立 provider。
3. 将 prompt / skill / agent 动态执行提取为独立 executor。
4. 让 dispatcher 只保留：
   - runtime context
   - action lookup
   - result normalization

## 验收标准

- 命令定义、schema 和 handler 不再双份维护。
- `ai/agent.py` 与其他消费者只依赖一个稳定 dispatcher surface。
- 新增 AI 命令时，不再需要同时修改多个大型中心文件。

## 提交检查点

- 检查点 1：唯一命令定义源确定并迁移完成。
- 检查点 2：dynamic tool provider / executor 切分完成。
- 检查点 3：dispatcher 收口与窄测验收完成。

## 风险与回退

风险：

- 命令面迁移若缺少兼容层，可能导致 agent 调用链瞬时失效。
- 动态工具执行边界如果设计不清，容易让 runtime context 在多个对象之间重复复制。

回退方式：

- 若一次性切换风险过高，先让新 registry/provider 并行存在，由 dispatcher 单向转接；待消费者切换完成后再删除旧实现。
- 若 dynamic tool executor 抽取后上下文契约不稳，先冻结旧接口并补契约测试，再继续替换。

## 延后到后续阶段的问题

- 剩余工作台页面、设置页和共享控件的最终深拆，转入 `Phase 36`。
- 功能优化前的结构闭环与质量门槛固化，转入 `Phase 37`。
