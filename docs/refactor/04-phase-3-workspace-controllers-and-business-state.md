# Phase 3：WorkspaceController 与页面业务状态

## 目标与完成定义

目标：

- 把页面业务状态从 `QWidget` 私有属性中移出。
- 为五个工作页建立稳定的 controller/state 结构。

完成定义：

- `Data`、`Chart`、`Process`、`Analysis`、`Digitize` 五页都拥有独立 `WorkspaceController + WorkspaceState`。
- 页面类只保留控件绑定、视图刷新与少量纯 UI 逻辑。

## 进入前提

- `Phase 2` 完成。
- 项目状态和领域服务边界已经稳定。

## 本阶段纳入的状态与边界

- `Process`
  - 已选输入
  - 当前 pipeline
  - 输出批次
  - 保存目标
- `Analysis`
  - 已选输入
  - 当前结果
  - 报告模板选择
  - 结果标签上下文
- `Chart`
  - 图表工作集
  - 曲线样式工作集
  - `FigureState`
  - 扩展实例状态
- `Digitize`
  - 当前图片
  - 当前曲线
  - 自动检测预览点
  - 导出目标
  - 校准上下文

## 本阶段禁止改动的区域

- 禁止把纯 UI 控件态强行升级为业务状态。
- 禁止把 controller 写成第二个页面类。
- 禁止绕过 `ProjectSession` 和服务层直接操作磁盘或项目数据。

## 目标接口/类型/运行时对象

- `DataWorkspaceController/State`
- `ChartWorkspaceController/State`
- `ProcessWorkspaceController/State`
- `AnalysisWorkspaceController/State`
- `DigitizeWorkspaceController/State`

每个 controller 至少承担：

- 接收树动作和 app 命令
- 维护本页业务状态
- 调用服务层完成业务动作
- 把可渲染状态暴露给页面 view

## 实施顺序

1. 先迁 `Data` 页和 `Process` 页。
2. 再迁 `Analysis` 页。
3. 再迁 `Chart` 页。
4. 最后迁 `Digitize` 页。
5. 每页迁移完成后，删除页面类中对应的业务状态字段和业务流程函数。

## 兼容/迁移策略

- 行为兼容优先，页面视觉结构可保持现状。
- 若某页迁移跨度过大，可暂时保留单一桥接层，但必须在本阶段内清理掉。

## 验收标准

- 页面业务逻辑不再依赖大批私有属性散落在 `QWidget` 中。
- 页面的业务输入、输出、当前选择、当前结果都能从对应 `WorkspaceState` 读取。
- 五个页面都能通过 controller 处理共享树动作。

## 提交检查点

- 检查点 1：`Data` 与 `Process` controller/state 落地。
- 检查点 2：`Analysis` controller/state 落地。
- 检查点 3：`Chart` controller/state 落地。
- 检查点 4：`Digitize` controller/state 落地。
- 检查点 5：页面类中对应业务状态字段被清理。

## 风险与回退办法

风险：

- 页面迁移过程中 view 与 state 双写。
- 控制器过厚，重新变成新的巨型对象。

回退办法：

- 如果出现双写，先暂停迁移，确认唯一状态源后再继续。
- controller 一旦开始持有 UI 控件引用，必须回退并重新收口职责。
