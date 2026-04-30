# Phase 25：扩展测试面与模块导出规范化

## 目标与完成定义

目标：

- 修复扩展运行时、命令层和模块导出面的遗留规范性问题，让测试真正反映当前架构而不是历史形态。
- 补足内聚但缺失的模块导出面，减少直接绕过包入口的隐式依赖。
- 统一低风险但持续制造噪声的命名与可见性不一致。

完成定义：

- 专家审查中成立的问题被系统化处理：
  - plot extension handler 过期测试契约
  - `dialogs/__init__.py` 与 `widgets/__init__.py` 导出不完整
  - `_HAS_MPL` / `HAS_MATPLOTLIB` 命名分裂
- 至少一组 extension runtime / command layer 测试被重写为面向当前契约。
- 模块入口与导出约定在文档中固定，不再继续“新模块绕过旧入口、旧入口长期失效”。

## 进入前提

- `Phase 24` 已完成多曲线处理与共享数值 primitive 的首轮性能收口。
- `2026-05-01` 的审查结果已确认：
  - `tests/test_backend.py::TestAnalysisEngine::test_invoke_plot_extension_handler_respects_plot_phases` 仍使用过期前提。
  - `dialogs/__init__.py`、`widgets/__init__.py` 的导出面与当前目录内容不一致。

## 本阶段纳入的状态与边界

- 纳入：
  - `tests/test_backend.py`
  - `tests/test_extension_runtime.py`
  - `tests/test_ui.py` 中与扩展/命令契约直接相关的部分
  - `ui/dialogs/__init__.py`
  - `ui/widgets/__init__.py`
  - `*_page_support.py` 的 matplotlib availability 常量
- 不纳入：
  - 大型业务流程重写
  - `project_tree.py` 深拆
  - 无证据的大范围重命名

## 本阶段禁止改动的区域

- 禁止为了“让测试通过”而回退已经稳定的 runtime 契约。
- 禁止把模块导出规范化扩张成整仓 import 风格重写。
- 禁止混入新的 UI 视觉改版。

## 目标接口/类型/运行时对象

- `invoke_plot_extension_handler`
- `invoke_analysis_extension_handler`
- `ui.dialogs`
- `ui.widgets`
- `HAS_MATPLOTLIB`

## 实施顺序

1. 更新过期的 runtime / command 测试前提。
2. 梳理 `dialogs` / `widgets` 当前应暴露的稳定入口。
3. 统一 matplotlib availability 命名约定。
4. 补少量 guardrail，防止入口和实现继续分叉。

## 核心问题清单

- 一部分测试仍以历史 handler 签名或历史执行模型为假设，容易制造假阴性或假阳性。
- 若包入口长期不更新，消费者会继续直接导入深层模块，削弱结构边界。
- `_HAS_MPL` 与 `HAS_MATPLOTLIB` 双命名增加理解成本，也削弱搜索与守护测试效果。

## 子阶段建议

### 25.1 Runtime Contract Test Repair

目标：

- 修复扩展 runtime 与命令层中已确认过期的测试。

验收要点：

- 至少一条 plot runtime 测试与一条 command 层测试被更新到当前契约。

### 25.2 Module Surface Normalization

目标：

- 补齐 `dialogs` / `widgets` 的稳定入口与导出规则。

验收要点：

- 目录中的主流稳定组件不再长期绕过包入口。
- 新增导出具有明确约束，而不是无差别暴露全部内部模块。

### 25.3 Small Consistency Guardrails

目标：

- 统一低风险命名分裂，并补守护测试。

验收要点：

- `HAS_MATPLOTLIB` 约定一致。
- 至少一条 guardrail 测试阻止新旧命名再次并存。

## 验收标准

- 测试修复反映当前真实契约，而不是恢复旧行为。
- 包入口与模块导出面有清晰、最小、稳定的约定。
- 小范围一致性清理不扩张为 import 风格大改。

## 提交检查点

- 检查点 1：过期 runtime / command 测试修复完成。
- 检查点 2：`dialogs` / `widgets` 导出面规范化完成。
- 检查点 3：命名一致性与 guardrail 补位完成。
- 检查点 4：阶段验收提交完成。

## 风险与回退办法

风险：

- 测试修复若混入行为回退，会掩盖真正的架构收益。
- 导出面若过度扩大，会重新引入隐式耦合。

回退办法：

- 若某个导出入口仍不稳定，先文档化为内部模块，不急于公开。
- 若某条过期测试背后仍有真实行为差异，先拆分为“契约修复”和“行为修复”两次提交。

## 延后到后续阶段的问题

- `extension_invoker.py` / `extension_loader.py` 的薄封装是否继续下沉。
- AI 包目录整合策略。
- 更完整的 extension 覆盖矩阵与生成式测试。
