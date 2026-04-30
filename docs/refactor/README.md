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

## 使用方式

- 实施前先读路线图，再只聚焦当前阶段文档。
- 实施中如果发现某项工作跨越多个阶段，必须回到路线图重新确认依赖，不允许临时改阶段顺序。
- 如果某阶段文档需要修订，应在修订提交中明确说明影响的后续阶段。
