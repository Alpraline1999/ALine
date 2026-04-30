# Phase 10：扩展运行时与接口契约重构

## 目标与完成定义

目标：

- 把当前扩展系统从“单文件混合职责 + 原始 handler 协议”重构为边界清晰、可测试、可 profiling、可批处理的 `ExtensionRuntime`。
- 让扩展接口与 `Phase 9` 的数组主数据对齐，支持数组原生输入、批处理、后台执行、错误隔离和能力声明。
- 收口扩展加载、注册、调用、兼容适配和状态报告的职责边界。

完成定义：

- `core.extension_api` 不再承担元数据、注册表、文件扫描、调用适配、load report、兼容导出等全部职责。
- 存在清晰的扩展 runtime 模块边界，例如：
  - contract / types
  - registry
  - loader
  - invoker
  - adapters
  - profiler / policy
- 扩展协议具备明确的能力声明机制，例如：
  - 是否支持数组原生输入
  - 是否支持批处理
  - 是否允许后台执行
  - 是否要求主线程 / UI 线程
- 内置扩展与页面侧调用路径，已迁移到新的 runtime 服务或兼容适配层。
- 旧的嵌套 `params["lines"]` / `params["lines"]["lines_list"]` 协议已从主执行链路移除，不再被处理 pipeline 与扩展运行时接受。
- `core.extension_loader.py`、`core.extension_invoker.py`、`processing/extension_tools.py` 若仍保留，已明确降级为受控兼容外观层，且不再承载主要实现。

## 进入前提

- `Phase 9` 完成。
- 运行时曲线主数据与数组视图契约已经稳定。

## 当前实现需要解决的问题

- `core/extension_api.py` 同时承担：
  - 类型定义
  - 注册表
  - 扫描加载
  - 调用适配
  - load report 格式化
  - 外部兼容函数导出
- `core/extension_loader.py` 与 `core/extension_invoker.py` 仍主要是转发层，边界并未真正落位。
- `extension_registry` 全局单例仍是主要耦合点，页面、服务和测试对其耦合较深。
- 扩展 handler 以原始 `list/dict` 为主，无法明确声明数组输入、批量输入、线程要求和缓存策略。
- 扩展运行时缺少统一的 timeout、错误隔离、profiling 和结果缓存策略。
- `processing/extension_tools.py` 仍保留兼容转发，说明旧接口路径尚未完全收口。
- `core/extension_runtime.py` 当前更接近轻量 façade，请求/结果对象已出现，但尚不足以证明 capability / policy / profiler 已经落位。
- 旧协议清理存在漏口，例如处理 pipeline 仍可能接受 `params["lines"]["lines_list"]` 形式的历史嵌套输入。

## 基于当前审查的补充说明

- 以当前仓库状态看，`Phase 10` 不能视为已完成。
- 已落地内容可视为本阶段的前置基础：
  - `CurveBuffer` / `SeriesArrayView` 已建立
  - `core.extension_runtime` 已提供最小 request / result / runtime façade
  - 运行时与协议清理已有首批窄测
- 但在以下收尾项关闭前，不得把本阶段标记为完成：
  - `core.extension_api` 从 monolith 缩减为兼容外观层或被稳定新模块替代
  - loader / registry / invoker / adapters / profiler / policies 边界真实落位
  - 处理 pipeline 不再接受旧嵌套 `lines` 协议
  - 兼容转发层的保留范围与退役计划已写清并由窄测覆盖

## 本阶段纳入的状态与边界

- 纳入：
  - 扩展运行时模块拆分
  - 扩展 descriptor / capability / contract 重建
  - 数组原生输入和批处理执行入口
  - 错误隔离、超时控制、profiling 钩子
  - 内置扩展迁移与旧兼容层收口
  - 旧嵌套 `lines` 协议的主链路清理与覆盖测试
- 不纳入：
  - 插件市场、网络分发、在线安装
  - 全新 UI 视觉设计
  - 与扩展无关的页面业务状态重构

## 本阶段禁止改动的区域

- 禁止在未定义能力协商前，让扩展直接依赖页面私有对象。
- 禁止把新的扩展协议设计成再次依赖 point-list 热路径复制。
- 禁止为追求兼容而继续扩大 `core.extension_api` 的职责范围。
- 禁止跳过 `Phase 9` 数组主数据契约，单独设计一套与之脱节的扩展输入协议。

## 目标接口/类型/运行时对象

- `ExtensionDescriptor`
- `ExtensionCapability`
- `ExtensionExecutionRequest`
- `ExtensionExecutionResult`
- `ProcessingInputView`
- `AnalysisInputView`
- `PlotInputContext`
- `DigitizeInputContext`
- `ExtensionRuntime`
- `ExtensionProfiler`
- `ExtensionExecutionPolicy`

## 推荐模块边界

- `core/extensions/contracts.py`
  - 描述元数据、能力标记、请求/结果类型
- `core/extensions/registry.py`
  - 只负责注册、查询、版本与唯一性约束
- `core/extensions/loader.py`
  - 只负责扫描、加载、错误收集、来源识别
- `core/extensions/invoker.py`
  - 只负责调用、批处理、超时与异常包装
- `core/extensions/adapters.py`
  - 负责 point-list、数组视图、分析结果、图表上下文之间的转换
- `core/extensions/profiler.py`
  - 负责 profiling 记录与性能样本输出
- `core/extensions/policies.py`
  - 负责线程模型、超时、缓存和隔离策略

## 接口策略

新的扩展接口不应继续停留在“只传 `lines` 和 `params`”：

- 处理/分析扩展：
  - 默认接收数组视图或曲线批量视图
  - 显式声明是否接受 legacy point-list
- 绘图扩展：
  - 接收稳定的绘图上下文对象
  - 不再默认依赖隐式 matplotlib 全局状态
- 数字化扩展：
  - 接收稳定的图像/校准上下文与输出契约
  - 可声明是否支持后台执行

兼容策略：

- 可以保留 legacy adapter 作为阶段性桥接。
- 但内置扩展应优先迁移到新协议。
- 旧兼容桥只作为过渡，不继续扩张。

## 实施顺序

1. 切分当前 monolith：
   - 先把 `core.extension_api` 中的 contracts / registry / loader / invoker 拆出独立模块，同时保留受控兼容导出。
2. 清理旧协议与兼容漏口：
   - 移除主执行链路对 `params["lines"]` / `params["lines"]["lines_list"]` 的接受。
   - 明确 `core.extension_loader.py`、`core.extension_invoker.py`、`processing/extension_tools.py` 的保留范围、替代入口和退役计划。
3. 建立 descriptor 与 capability 协议：
   - 让扩展显式声明输入类型、批处理能力、线程要求和输出类型。
4. 对齐 `Phase 9` 数据视图：
   - 让处理、分析、绘图、数字化统一接入数组主数据或稳定上下文对象。
5. 增加执行治理：
   - profiling
   - timeout
   - 错误隔离
   - 缓存键
   - 批处理入口
6. 迁移内置扩展与页面调用链：
   - 逐类迁移处理、分析、绘图、数字化扩展。
7. 收口兼容层与窄测：
   - 清理纯转发模块和不再需要的旧签名桥接路径。
   - 补齐 loader / invoker / pipeline / 旧协议拒绝路径的窄测。

## 验收标准

- `core.extension_api` 不再是主要实现承载文件。
- 至少一类扩展已完成从 legacy handler 到新 runtime contract 的迁移闭环。
- 新 runtime 可以表达数组输入、批处理、线程模型和错误隔离策略。
- 页面/服务对扩展系统的调用边界更稳定，测试不再大量耦合单一全局模块。
- 旧兼容路径若仍保留，其范围和退役计划已明确。
- 主执行链路不再接受旧嵌套 `params["lines"]` 协议，相关拒绝路径有窄测覆盖。
- `core.extension_loader.py`、`core.extension_invoker.py`、`processing/extension_tools.py` 不再作为“主要实现藏身处”；若保留，仅承担受控兼容导出。

## 提交检查点

- 检查点 1：runtime 模块拆分与兼容导出落地。
- 检查点 2：旧协议漏口清理与 compatibility 范围落档。
- 检查点 3：capability / request / result 契约落地。
- 检查点 4：至少一类扩展迁移到新协议。
- 检查点 5：执行治理、兼容层收口与窄测闭环完成。

## 风险与回退办法

风险：

- 一次性重写所有扩展协议，导致内置扩展大面积失效。
- 新协议设计过度复杂，迁移成本超过收益。
- 运行时治理逻辑分散，最终又回到单文件堆积。

回退办法：

- 先保留受控 legacy adapter，按类别分批迁移扩展。
- 如果某项能力声明过细，先保留核心 capability 集合，避免过度建模。
- 如果模块拆分后测试覆盖不足，优先补充 runtime 窄测，再继续扩张迁移范围。
