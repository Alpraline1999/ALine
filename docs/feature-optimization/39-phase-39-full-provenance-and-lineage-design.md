# Phase 39：全量来源追溯与节点血缘设计

## 目标与完成定义

**目标**：为数据节点、绘图节点、分析结果建立统一的 lineage / provenance 结构，使处理、数字化、绘图、分析都具备完整可追溯性。

**完成定义**：
- 能明确表达“当前节点来自哪里、经过哪些步骤、使用了哪些参数、依赖哪些上游对象”
- 为后续复跑、审计、比较、AI 上下文引用提供统一数据基础
- 形成明确的数据模型与 UI 展示方案

## 为什么单独成 phase

- 这不是简单的“备注增强”或“保存更多字段”
- 它会影响：
  - schema
  - project persistence
  - process / analysis / digitize / chart 四条链路
  - 节点详情展示
  - 后续 AI 上下文模型

## 设计目标

### 1. 血缘结构统一

建议统一抽象：

- `inputs`: 上游节点/对象引用
- `operation`: 执行动作类型，例如 import / digitize / pipeline / plot / analysis
- `parameters`: 关键参数快照
- `artifacts`: 关联模板、扩展配置、样式模板、报告模板等
- `environment`: 时间、版本、扩展版本、运行上下文

### 2. 追溯既可读又可机器消费

- 节点详情面板中可直接阅读
- 数据结构可供复跑和 AI 调用

### 3. 区分轻量摘要与完整日志

- UI 默认显示摘要
- 数据层可保留完整 provenance record

## 关键设计问题

- 哪些对象需要持久化完整 lineage
- 节点删除、复制、导出、另存后如何处理 provenance
- 同一节点的多次派生是否采用 append-only 事件流还是 latest snapshot
- 结果复跑时是否允许 provenance 反向生成执行计划

## 验收要点

- 有完整的数据模型草案
- 有 UI 展示草案
- 有持久化兼容策略
- 有与 Phase 40 AI 设计的接口边界说明

## 本阶段暂不拆任务

- 该能力影响面过大，需先稳定设计文档
