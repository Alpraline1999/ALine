# Phase 17：长流程业务编排与分析工作台收口

## 目标与完成定义

目标：

- 处理仍然集中在长函数、长分支和流程拼装中的业务模块，使分析、导入、导出、处理这几条主业务链更稳定可扩展。
- 把“业务决策”“结果模型”“扩展接入”“UI 展示”之间的边界进一步拉开。
- 为后续性能优化、测试覆盖扩张和功能演进建立更可预测的编排结构。

完成定义：

- `analysis_engine` 中的长分支与结果拼装逻辑开始分层，不再继续堆在单一模块里。
- `import_dialog`、`export_flow`、`data_engine` 等流程模块的计划/解析/执行边界更清晰。
- 分析、导入、导出结果模型与扩展接口之间的适配关系更稳定。
- 后续新增流程功能有明确落点，而不是继续往长函数里追加 `if/elif`。

## 进入前提

- `Phase 16` 完成，静态质量和异常策略已经收口到可维护水平。
- UI 页面和共享控件边界相对稳定，不再频繁回灌到业务流程模块。

## 本阶段纳入的状态与边界

- 纳入：
  - `core/analysis_engine.py`
  - `processing/data_engine.py`
  - `ui/dialogs/import_dialog.py`
  - `ui/dialogs/export_flow.py`
  - `core/exporter.py`
  - 相关结果模型、导入解析模型、导出计划对象
  - 与这些流程直接耦合的少量 UI/workspace glue
- 不纳入：
  - 扩展协议大改版
  - 新的分析算法研究
  - 全新导入/导出产品能力
  - 测试框架重写

## 本阶段禁止改动的区域

- 禁止把长流程重构演变成算法行为重写。
- 禁止为了消除 `if/elif` 而引入过度抽象的空壳策略体系。
- 禁止把 UI 展示细节重新耦合回 `core` 和 `processing`。
- 禁止跨阶段去重构与主流程无关的 widget 样式问题。

## 目标接口/类型/运行时对象

- `AnalysisPlan`
- `AnalysisResultBuilder`
- `ImportPlan`
- `ImportPreviewParser`
- `ExportPlan`
- `ExportExecutionService`
- `PipelineExecutionPlan`

## 实施顺序

1. 先处理 `analysis_engine`：
   - 分析类型注册/元数据
   - 结果模型与结果拼装
   - 报告模板上下文
2. 再处理导入/导出流程：
   - import plan / preview parse / target resolve
   - export plan / execution
3. 最后处理 `data_engine` 与流程 glue：
   - 参数标准化
   - pipeline 执行计划
   - 扩展入口与错误反馈边界

## 核心问题清单

- `analysis_engine` 继续承担过多分析类型分支、结果组装和模板上下文逻辑。
- `import_dialog` 和 `export_flow` 流程长、状态多，适合拆成计划对象和执行服务。
- `data_engine` 仍然承担较重的参数规范、线协议适配和 pipeline 执行 glue。
- 这些模块目前能工作，但扩展新能力的边际成本仍然偏高。

## 子阶段建议

### 17.1 Analysis Workbench Normalization

目标：

- 收口分析类型元数据、结果装配和模板上下文生成逻辑。

建议验证：

- `tests/test_backend.py -k "analysis"`
- 直接命中的 analysis UI 窄测

### 17.2 Import / Export Flow Decomposition

目标：

- 把导入预览解析、目标选择、导出计划和执行动作从对话框类中拆出。

建议验证：

- `tests/test_backend.py -k "import or export"`
- 命中的对话框窄测

### 17.3 Data Engine Flow Cleanup

目标：

- 收口 pipeline 参数标准化、执行计划和结果 glue。

建议验证：

- `tests/test_extension_runtime.py`
- `tests/test_backend.py -k "pipeline or processing"`

## 验收标准

- 至少一条长流程主链完成分层，不再继续把新逻辑堆进原长函数。
- 结果模型、计划对象和执行服务的职责边界清晰。
- 窄测覆盖新的编排边界，而不是只验证最终 UI 行为。

## 提交检查点

- 检查点 1：analysis workbench 首轮收口完成。
- 检查点 2：import/export flow 首轮拆分完成。
- 检查点 3：data engine flow cleanup 完成。
- 检查点 4：阶段验收与后续边界文档化完成。

## 风险与回退办法

风险：

- 业务流程重构时误带入行为差异。
- 计划对象抽象过度，导致调用链更难读。

回退办法：

- 每条主流程都按计划对象/执行对象/结果对象逐步拆出，避免一次性改完。
- 若某次抽象收益不明显，退回到薄 service + 明确参数，而不是继续做大框架。

## 延后到后续阶段的问题

- 更大范围的功能策略化
- 扩展测试覆盖体系扩张
- 与性能 profiling 联动的更深层业务优化
