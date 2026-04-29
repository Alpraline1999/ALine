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

## 文档职责

- `00-refactor-roadmap.md`
  - 只负责解释为什么重构、总目标是什么、阶段之间如何依赖。
  - 不包含逐步实现动作，不直接作为实施清单。
- `01` 到 `08`
  - 每份文档对应一个可执行阶段。
  - 每份文档都必须独立说明进入前提、目标边界、验收标准、提交检查点和回退方式。

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

## 使用方式

- 实施前先读路线图，再只聚焦当前阶段文档。
- 实施中如果发现某项工作跨越多个阶段，必须回到路线图重新确认依赖，不允许临时改阶段顺序。
- 如果某阶段文档需要修订，应在修订提交中明确说明影响的后续阶段。
