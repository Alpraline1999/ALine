# Phase 32：剩余 Monolith 与服务编排拆分

## 目标与完成定义

目标：

- 在 UI surface、包面和质量门槛都稳定后，继续处理剩余的大型 monolith 和服务编排中心。
- 优先收口 `project_manager.py`、`ai.command_layer`、`data_page.py`、`chart_page.py` 这类仍然偏大的核心文件。
- 防止系统在完成多轮局部优化后，再次把复杂度集中回少数超级模块。

完成定义：

- `ProjectManager` 的超大服务面被继续拆成明确 service / repository / mutation handler 边界。
- `ai.command_layer` 不再作为混合型编排中心持续增长。
- `DataPage` 与 `ChartPage` 的壳层文件进一步缩短，复杂交互被提取到 support/panel/controller 模块。

## 进入前提

- `Phase 29` 到 `Phase 31` 已完成 UI surface、包面与质量门槛收口。
- 当前剩余大型模块的问题已具备稳定测试和单一入口前提。

## 本阶段纳入的范围

- `core/project_manager.py`
- `ai/command_layer.py` 及其直接依赖
- `ui/pages/data_page.py`
- `ui/pages/chart_page.py`
- 与上述模块直接相关的 support/service/controller/presenter 模块

## 本阶段不纳入的范围

- 新增业务能力
- 再次改写扩展协议
- 非热点数值算法优化

## 本阶段禁止事项

- 禁止把“瘦身”理解成简单移动代码，而不改变职责边界。
- 禁止把业务状态重新分散回 UI 私有属性或全局单例。
- 禁止在没有消费者测试的情况下拆 `ProjectManager` 或 `command_layer`。

## 核心问题清单

- `ProjectManager` 仍然是项目层中心对象，虽然已有服务提取，但剩余职责仍偏多。
- `ai.command_layer` 仍可能继续吸收命令路由、工具管理和上下文拼装细节。
- `DataPage`、`ChartPage` 文件体量大，后续任何修复都容易跨越无关关注点。

## 实施顺序

1. 先按只读查询、状态变更、批处理动作拆 `ProjectManager` 服务面。
2. 收口 `ai.command_layer` 的命令注册、执行上下文与工具管理边界。
3. 对 `DataPage`、`ChartPage` 做第二轮 support/controller/panel 拆分。
4. 用窄测验证新边界，不允许只做文件移动。

## 验收标准

- 每个被拆模块都能回答：
  - 壳层现在只负责什么
  - 被提取模块真正承担什么职责
  - 相关测试从哪里覆盖
- `ProjectManager` 与 `ai.command_layer` 不再是继续吸纳新逻辑的默认落点。
- `DataPage` 与 `ChartPage` 的壳层复杂度明显下降，局部问题可以在 support 模块中独立修复。

## 提交检查点

- 检查点 1：`ProjectManager` / `ai.command_layer` 边界切分完成。
- 检查点 2：`DataPage` / `ChartPage` 第二轮拆分完成。
- 检查点 3：窄测与阶段验收提交完成。

## 风险与回退

风险：

- 大模块拆分若没有前置质量门槛，容易一次引入多类回归。
- `ProjectManager` 与 `command_layer` 都有广泛消费者，拆分顺序错误会放大连锁影响。

回退方式：

- 若某步拆分影响过大，先保留新 service 模块并缩小接入面，不强行一次替换所有消费者。
- 若 `DataPage` / `ChartPage` 某次提取没有明显降低复杂度，应回退该提取并重新按职责切分。

## 延后到后续阶段的问题

- 更长期的 profiling 平台化、CI 扩展和设计系统沉淀，可在 `Phase 32` 之后单独规划。
