# ALine 重构文档索引

本目录是 ALine 架构重构的唯一实施依据。后续所有重构阶段、检查点提交、验收与回退，都以这里的文档为准。

## 阅读顺序

1. [00-refactor-roadmap.md](00-refactor-roadmap.md)
2. [01-phase-0-baseline-and-guardrails.md](01-phase-0-baseline-and-guardrails.md)
3. [02-phase-1-app-shell-and-runtime-boundaries.md](02-phase-1-app-shell-and-runtime-boundaries.md)
4. [03-phase-2-project-session-and-domain-services.md](03-phase-2-project-session-and-domain-services.md)
5. [04-phase-3-workspace-controllers-and-business-state.md](04-phase-3-workspace-controllers-and-business-state.md)
6. [05-phase-4-extension-runtime-and-global-assets.md](05-phase-4-extension-runtime-and-global-assets.md)
7. [06-phase-5-cleanup-file-splitting-and-dead-path-removal.md](06-phase-5-cleanup-file-splitting-and-dead-path-removal.md)
8. [07-phase-6-quality-gates-and-test-restructure.md](07-phase-6-quality-gates-and-test-restructure.md)
9. [08-phase-7-ui-state-performance-and-polish.md](08-phase-7-ui-state-performance-and-polish.md)
10. [10-phase-8-large-curve-performance-and-extension-optimization.md](10-phase-8-large-curve-performance-and-extension-optimization.md)
11. [11-phase-9-runtime-array-data-model.md](11-phase-9-runtime-array-data-model.md)
12. [12-phase-10-extension-runtime-and-api-hardening.md](12-phase-10-extension-runtime-and-api-hardening.md)
13. [13-phase-11-large-curve-hot-path-and-memory-hardening.md](13-phase-11-large-curve-hot-path-and-memory-hardening.md)
14. [14-phase-12-ui-page-decomposition-and-shell-normalization.md](14-phase-12-ui-page-decomposition-and-shell-normalization.md)
15. [15-phase-13-codebase-normalization-and-ui-consistency.md](15-phase-13-codebase-normalization-and-ui-consistency.md)
16. [16-phase-12-13-execution-summary.md](16-phase-12-13-execution-summary.md)
17. [17-phase-14-redundancy-elimination-and-architectural-consistency.md](17-phase-14-redundancy-elimination-and-architectural-consistency.md)
18. [18-phase-15-monolith-decomposition-and-shared-widget-extraction.md](18-phase-15-monolith-decomposition-and-shared-widget-extraction.md)
19. [19-phase-16-static-quality-and-reliability-hardening.md](19-phase-16-static-quality-and-reliability-hardening.md)
20. [20-phase-17-domain-flow-and-analytical-workbench-normalization.md](20-phase-17-domain-flow-and-analytical-workbench-normalization.md)
21. [21-phase-17-execution-summary.md](21-phase-17-execution-summary.md)
22. [22-phase-18-shared-processing-foundation-and-dependency-direction-repair.md](22-phase-18-shared-processing-foundation-and-dependency-direction-repair.md)
23. [23-phase-19-expression-engine-and-processing-contract-normalization.md](23-phase-19-expression-engine-and-processing-contract-normalization.md)
24. [24-phase-20-project-session-and-command-orchestration-decomposition.md](24-phase-20-project-session-and-command-orchestration-decomposition.md)
25. [25-phase-21-ui-monolith-completion-and-workspace-surface-hardening.md](25-phase-21-ui-monolith-completion-and-workspace-surface-hardening.md)
26. [26-phase-22-large-workspace-performance-and-data-virtualization.md](26-phase-22-large-workspace-performance-and-data-virtualization.md)
27. [27-phase-22-execution-summary.md](27-phase-22-execution-summary.md)
28. [28-phase-23-runtime-regression-and-contract-guardrails.md](28-phase-23-runtime-regression-and-contract-guardrails.md)
29. [29-phase-24-multiline-processing-performance-and-numeric-primitives.md](29-phase-24-multiline-processing-performance-and-numeric-primitives.md)
30. [30-phase-25-extension-tests-and-module-surface-normalization.md](30-phase-25-extension-tests-and-module-surface-normalization.md)
31. [31-phase-26-project-tree-and-ui-interaction-surface-decomposition.md](31-phase-26-project-tree-and-ui-interaction-surface-decomposition.md)
32. [32-phase-27-ui-theme-and-paint-regression-audit.md](32-phase-27-ui-theme-and-paint-regression-audit.md)

## 文档职责

- `00-refactor-roadmap.md`
  - 只负责解释为什么重构、总目标是什么、阶段之间如何依赖。
  - 不包含逐步实现动作，不直接作为实施清单。
- `01` 到 `08`
  - 每份文档对应一个可执行阶段。
  - 每份文档都必须独立说明进入前提、目标边界、验收标准、提交检查点和回退方式。
- `10-phase-8-large-curve-performance-and-extension-optimization.md`
  - 定义大曲线、大数据量场景的 profiling、抽样、缓存、后台执行和局部性能优化阶段。
  - 该阶段默认承接 `Phase 7` 之后的性能硬化工作，并为后续运行时数组化提供证据。
- `11-phase-9-runtime-array-data-model.md`
  - 定义运行时曲线主数据数组化与热路径表示收口阶段。
  - 该阶段负责把性能敏感的数值曲线主数据迁移到数组后端，而不是把所有 `list` 全面替换为 `numpy`。
- `12-phase-10-extension-runtime-and-api-hardening.md`
  - 定义扩展运行时、扩展接口契约、批处理与隔离策略的重构阶段。
  - 该阶段负责收口 `core.extension_api` 的职责边界，并让扩展运行时与 `Phase 9` 的数组主数据对齐。
- `13-phase-11-large-curve-hot-path-and-memory-hardening.md`
  - 定义 `Phase 10` 完成后的大曲线/大数据量热路径收口阶段。
  - 该阶段负责把图表、处理、分析、数字化与扩展执行主链路尽量收口为 buffer-first 流动，并控制复制、阻塞和内存占用。
- `14-phase-12-ui-page-decomposition-and-shell-normalization.md`
  - 定义超大 UI 页面拆分与页面壳层标准化阶段。
  - 该阶段负责拆分 `chart_page`、`digitize_page`、`analysis_page`、`process_page`、`settings_page` 等超大文件，并统一页面装配边界。
- `15-phase-13-codebase-normalization-and-ui-consistency.md`
  - 定义代码规范、冗余收口与 UI 风格一致性阶段。
  - 该阶段负责清理兼容转发、重复适配、命名与导出不一致问题，并沉淀共享 UI token / 组件 / 状态呈现约定。
- `17-phase-14-redundancy-elimination-and-architectural-consistency.md`
  - 定义 `Phase 13` 之后的高收益重复实现清理与架构一致性硬化阶段。
  - 该阶段负责处理 extension handler 重复、ProjectManager 内部重复服务、matplotlib 启动重复、小型死转发层，以及 DataPage 前提澄清后的后续边界。
- `18-phase-15-monolith-decomposition-and-shared-widget-extraction.md`
  - 定义 `Phase 14` 之后的超大页面与共享控件深拆阶段。
  - 该阶段负责继续拆分 `DataPage`、`project_tree`、`image_viewer`、`extension_options_form` 等高复杂度 monolith，并把页面状态代理和共享控件职责进一步收口。
- `19-phase-16-static-quality-and-reliability-hardening.md`
  - 定义静态质量、异常策略和 UI 交互回调硬化阶段。
  - 该阶段负责收口 `ruff` 高噪声问题、静默吞异常、具名回调替换、导入与导出面漂移，以及 state bridge 代理模式的可维护性问题。
- `20-phase-17-domain-flow-and-analytical-workbench-normalization.md`
  - 定义分析、导入、导出等长流程业务模块的结构收口阶段。
  - 该阶段负责整理 `analysis_engine`、`import_dialog`、`export_flow`、`data_engine` 等长函数/长分支模块，使业务编排、结果模型和扩展接入边界更稳定。
- `22-phase-18-shared-processing-foundation-and-dependency-direction-repair.md`
  - 定义共享处理基础、低风险一致性噪声与跨层依赖方向纠偏阶段。
  - 该阶段负责修复 `processing` / `extensions` 共享 helper 的层次反转，消除 extension type 循环依赖，并统一 `process_page` 的 bootstrap 入口。
- `23-phase-19-expression-engine-and-processing-contract-normalization.md`
  - 定义表达式执行、参数解析与处理扩展契约规范化阶段。
  - 该阶段负责收口裸 `eval`、重复 `_as_float` 和 transform/pairwise 类扩展的共享执行边界。
- `24-phase-20-project-session-and-command-orchestration-decomposition.md`
  - 定义 `ProjectManager` 与 `ai.command_layer` 的大型编排拆分阶段。
  - 该阶段负责提炼 project services、命令 registry / handlers，并限制单文件业务编排继续增长。
- `25-phase-21-ui-monolith-completion-and-workspace-surface-hardening.md`
  - 定义剩余超大 UI 页面与 workspace surface 的收尾硬化阶段。
  - 该阶段负责继续拆分 `DataPage`、`chart_page`、`digitize_page`、`analysis_page`、`process_page` 和 `MainWindow` 的路由边界。
- `26-phase-22-large-workspace-performance-and-data-virtualization.md`
  - 定义大工作区、超大曲线与大数据量链路的性能与虚拟化阶段。
  - 该阶段负责建立 profiling 样本、收口 workspace virtualization / progressive rendering，并固定“非热点不强制 numpy 化”的规则。
- `28-phase-23-runtime-regression-and-contract-guardrails.md`
  - 定义 `Phase 22` 之后的运行时回归扫尾与契约护栏阶段。
  - 该阶段负责收口 late-stage refactor 引入的回调签名漂移、workspace state proxy 漏接、过期测试契约和小范围死代码。
- `29-phase-24-multiline-processing-performance-and-numeric-primitives.md`
  - 定义多曲线处理性能与共享数值 primitive 收口阶段。
  - 该阶段负责继续优化 `multi_curve_mean`、`pairwise_compute`、对齐/插值共享 helper 与多输入 pipeline 的复制预算。
- `30-phase-25-extension-tests-and-module-surface-normalization.md`
  - 定义扩展测试面、模块导出和小范围命名一致性阶段。
  - 该阶段负责更新过期 runtime 测试、补齐 `dialogs` / `widgets` 入口，并统一低风险命名分裂。
- `31-phase-26-project-tree-and-ui-interaction-surface-decomposition.md`
  - 定义项目树与页面交互面继续拆分的阶段。
  - 该阶段负责收口导入/导出 target binding、树命令绑定点和页面目标节点解析。
- `32-phase-27-ui-theme-and-paint-regression-audit.md`
  - 定义主题切换链路、页面局部主题刷新、自定义绘制/委托运行时安全的全面检查阶段。
  - 该阶段负责建立 theme switch 性能样本、paint/delegate/import 安全扫描和 settings/UI 主题一致性检查矩阵。

## 阶段进入规则

- 任何阶段开始前，必须先确认上一阶段已经满足其“完成定义”和“验收标准”。
- 不允许跳过 `Phase 0` 与 `Phase 1` 直接拆大文件或清理 UI 细节态。
- 只有在阶段文档明确允许的范围内，才可以顺手调整相邻模块。

## 阶段退出规则

- 每个阶段结束时，必须完成本阶段文档中的：
  - 完成定义
  - 验收标准
  - 提交检查点
- 阶段结束后，必须形成一个阶段总结提交，提交方式遵循 `.github/skills/important-change-commit/SKILL.md`。

## 阶段验收文档约定

- 本轮不再额外创建独立的“验收文档”文件。
- 每个阶段文档内部的“验收标准”章节就是该阶段的正式验收依据。
- `Phase 0` 中建立的架构规则和测试护栏，对后续所有阶段持续生效。

## 历史文档处理

- 根目录下的 `plan_pro-v1.md`、`plan_pro-v2.md` 仅保留为历史记录。
- 它们不再作为当前重构阶段的实施依据，也不能覆盖本目录中的任何约束。

## 提交与节奏

- 每个阶段至少包含三类提交节点：
  - 阶段开始后的第一个已验证结构切片
  - 阶段中的一个或多个重要检查点
  - 阶段完成后的验收提交
- 这些节点必须在对应阶段文档的“提交检查点”章节中逐项兑现。

## 运行时状态总原则

- 本轮架构重构优先处理业务运行时状态：
  - 图表工作集、处理输入、分析结果上下文、数字化当前图片/曲线/导出目标、`FigureState`
- 后置到 `Phase 7` 的纯 UI 状态：
  - splitter 尺寸、滚动位置、tooltip 生命周期、当前 tab 视觉态、教学提示临时状态、预览工具栏显隐
- 后置到 `Phase 8` 的性能优化：
  - 大曲线 profiling、抽样、缓存、后台执行、局部刷新
- 后置到 `Phase 9` 的运行时主数据优化：
  - 曲线主数据数组化
  - `list(point)` / `x,y` / `series payload` 重复转换收口
  - 热路径 `numpy` / 数组视图统一适配
- 后置到 `Phase 10` 的扩展运行时优化：
  - 扩展接口契约重构
  - 扩展批处理、数组原生输入、超时隔离、profiling 钩子
  - 扩展加载器 / 调用器 / 注册表边界收口
- 后置到 `Phase 11` 的大曲线热路径收口：
  - buffer-first 主链路
  - 大曲线渲染渐进化与局部物化
  - 大批量处理/分析/数字化的复制与内存占用控制
- 后置到 `Phase 12` 的超大页面拆分：
  - 页面壳层、actions、panels、workspace bridge 分层
  - `MainWindow` 与页面之间的调用边界进一步收口
- 后置到 `Phase 13` 的规范与一致性收尾：
  - 兼容层与死路径清理
  - 重复 helper / adapter 收口
  - UI token、状态文案和交互样式统一
- 后置到 `Phase 14` 的重复实现与一致性硬化：
  - extension runtime / api 重复实现消除
  - 共享基础设施重复初始化收口
  - `ProjectManager` 内部服务化提炼
  - `DataPage` 前提校正后的页面边界和状态整理
- 后置到 `Phase 15` 的深层 monolith 拆分：
  - `DataPage` / `project_tree` / `image_viewer` / `extension_options_form` 等共享控件与页面深拆
  - 页面 state bridge / presenter / panel factory 进一步固化
- 后置到 `Phase 16` 的静态质量与可靠性硬化：
  - `ruff` 高噪声债务
  - 静默异常策略分级
  - lambda / 闭包回调具名化
  - state proxy / 导入导出面规范化
- 后置到 `Phase 17` 的长流程业务编排收口：
  - `analysis_engine` / `import_dialog` / `export_flow` / `data_engine` 长分支与长函数重构
  - 结果模型、导入解析、导出计划与扩展入口边界统一

## 使用方式

- 实施前先读路线图，再只聚焦当前阶段文档。
- 实施中如果发现某项工作跨越多个阶段，必须回到路线图重新确认依赖，不允许临时改阶段顺序。
- 如果某阶段文档需要修订，应在修订提交中明确说明影响的后续阶段。
