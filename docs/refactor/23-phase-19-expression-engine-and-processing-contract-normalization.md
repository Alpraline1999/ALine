# Phase 19：表达式执行与处理扩展契约规范化

## 目标与完成定义

目标：

- 收口当前分散在 `data_engine` 与多个处理扩展中的表达式执行逻辑，减少裸 `eval` 散布和重复上下文构造。
- 把跨处理/绘图/分析扩展重复出现的数值参数解析 helper 统一到受控入口。
- 稳定 transform / pairwise / formula 类扩展的错误反馈与参数校验边界，为后续性能与扩展演进建立一致契约。

完成定义：

- 表达式求值不再散落在多个业务文件中，至少已有一个受控执行入口负责上下文、允许符号集与错误映射。
- `processing/data_engine.py`、`extensions/processing/transform.py`、`extensions/processing/pairwise_compute.py` 的表达式执行路径完成首轮统一。
- 多处重复的 `_as_float` 或等价数值解析 helper 开始收口为共享解析工具，而不是继续在扩展文件中横向复制。
- 表达式执行错误、参数错误、空输入错误的反馈风格更稳定，避免相邻扩展各自定义异常语义。

## 进入前提

- `Phase 18` 已完成，处理基础 helper 与依赖方向已经收口到可维护水平。
- 本阶段只规范表达式执行和参数契约，不变更用户可见业务流程，也不引入新的表达式语言。

## 本阶段纳入的状态与边界

- 纳入：
  - `processing/data_engine.py`
  - `extensions/processing/transform.py`
  - `extensions/processing/pairwise_compute.py`
  - 直接相关的处理扩展 helper
  - `extensions/plot/*` 中重复的 `_as_float` helper
  - `extensions/analysis/spectrum_analysis.py`
  - 新的表达式执行与参数解析模块
- 不纳入：
  - 新的 DSL 设计
  - 沙箱系统重写
  - AI skill 执行器安全体系重构
  - 与表达式无关的扩展 UI 改版

## 本阶段禁止改动的区域

- 禁止为了“安全”而临时改写用户现有表达式语法。
- 禁止把表达式执行抽象成空壳策略体系或引入难以理解的迷你解释器框架。
- 禁止继续在业务文件中复制第二套 `_as_float` / `_safe_globals` / 上下文构造逻辑。
- 禁止把所有参数验证都塞回单一扩展注册表对象。

## 目标接口/类型/运行时对象

- `ExpressionExecutionService`
- `ExpressionContextBuilder`
- `TransformExpressionPlan`
- `FloatParamParser`
- `ExtensionParamNormalizer`

## 实施顺序

1. 先抽取共享参数解析入口：
   - `_as_float` / 数值解析
   - 常见缺省值和错误文案
2. 再抽取表达式执行入口：
   - 允许符号集
   - 上下文构造
   - 结果类型检查
3. 再统一处理扩展主链路：
   - `data_engine`
   - `transform`
   - `pairwise_compute`
4. 最后把相邻扩展的参数与错误反馈风格对齐

## 核心问题清单

- `processing/data_engine.py` 与多个处理扩展中仍分散存在裸 `eval` 调用点。
- 表达式上下文构造逻辑重复，且错误边界并不统一。
- `_as_float` 在多个 plot / analysis / processing 扩展中重复出现，形成低价值复制。
- 扩展参数错误、表达式错误与空数据错误的提示风格不一致，增加调试成本。

## 子阶段建议

### 19.1 Shared Param Parsing

目标：

- 把跨扩展重复出现的数值参数解析收口到共享工具。

验收要点：

- `_as_float` 类 helper 不再在多个扩展文件中继续复制扩散。
- 缺省值与错误处理约定有统一入口。

建议验证：

- 命中的 plot / analysis / processing 扩展窄测
- `py_compile` 相关扩展文件

### 19.2 Expression Execution Service

目标：

- 建立受控表达式执行入口，统一安全上下文、类型检查与错误映射。

验收要点：

- 业务文件中的裸 `eval` 调用显著减少。
- 表达式执行错误可以映射到稳定、可理解的用户提示或 warning。

建议验证：

- `tests/test_backend.py -k "transform or pairwise or pipeline"`
- 命中的表达式行为窄测

### 19.3 Processing Contract Normalization

目标：

- 把 transform / pairwise 一类扩展的参数、输入与输出契约做首轮统一。

验收要点：

- `data_engine` 与扩展处理器之间的表达式相关 glue 更薄。
- 新增表达式型处理扩展时，有明确的共享执行与参数入口。

建议验证：

- `tests/test_extension_runtime.py`
- 直接命中的 processing/backend 窄测

## 验收标准

- 表达式执行的共享入口已经存在，并承接至少一条主业务链。
- 重复数值解析 helper 已开始收口，不再继续横向复制。
- 表达式/参数错误反馈更稳定，而不是每个扩展自说自话。
- 本阶段不改变项目文件格式，也不引入新的表达式语法破坏。

## 提交检查点

- 检查点 1：共享参数解析入口落地。
- 检查点 2：表达式执行服务首轮接入完成。
- 检查点 3：processing contract 首轮统一完成。
- 检查点 4：阶段验收与后续边界文档化完成。

## 风险与回退办法

风险：

- 表达式执行收口可能改变边缘错误行为或类型容错。
- 过度抽象会让简单扩展的阅读成本变高。

回退办法：

- 若统一执行入口导致行为不清晰，退回到“共享 helper + 显式调用”，不要继续做大框架。
- 若个别扩展有特殊参数需求，允许保留薄适配层，但必须复用共享解析与执行基础。

## 延后到后续阶段的问题

- `ProjectManager` / `ai.command_layer` 的大型编排拆分
- 剩余超大 UI 页面和 `MainWindow` surface 的收口
- 大工作区与超大曲线场景的性能、虚拟化和后台写回优化
