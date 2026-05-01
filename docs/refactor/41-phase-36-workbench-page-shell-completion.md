# Phase 36：Remaining Workbench Page Shell Completion

## 目标与完成定义

目标：

- 完成 `DigitizePage`、`AnalysisPage`、`ProcessPage`、`SettingsPage` 等剩余大型页面壳层的收尾深拆。
- 处理仍然偏大的共享控件/对话框，如 `extension_options_form`、`import_dialog`、`export_flow`、`image_viewer`。
- 统一页面级别的 selection / preview / export / extension panel 编排模式。

完成定义：

- 剩余大型页面不再把数据选择、结果保存、导出计划、主题刷新、扩展面板联动和预览渲染同时塞在单文件壳层中。
- 共享控件和对话框的职责边界进一步清晰，页面不再依赖内部细节才能完成常见流程。
- 跨页面复用的 UI 行为有明确 support/presenter/coordinator 落点。

## 进入前提

- `Phase 33` 到 `Phase 35` 已完成项目树/数据页、`ProjectManager` façade 和 AI 命令面的收口。
- 页面当前功能链路稳定，适合做第二轮以可维护性为主的深拆。

## 本阶段纳入的范围

- `ui/pages/digitize_page.py`
- `ui/pages/analysis_page.py`
- `ui/pages/process_page.py`
- `ui/pages/settings_page.py`
- `ui/widgets/extension_options_form.py`
- `ui/widgets/image_viewer.py`
- `ui/dialogs/import_dialog.py`
- `ui/dialogs/export_flow.py`
- 与上述页面/控件直接相关的 support / presenter / coordinator 模块

## 本阶段不纳入的范围

- 新工作台功能
- 大规模视觉改版
- 新的导入导出协议

## 本阶段禁止事项

- 禁止把页面内部复杂度简单挪到单一 support 文件，形成新的 monolith。
- 禁止继续在页面中直接做项目目标节点解析或跨页规则判断。
- 禁止为了追求“短文件”，牺牲页面状态流的可读性。

## 核心问题清单

- `DigitizePage` 仍混合 viewer 工具、自动识别、导出目标推导、曲线编辑、右侧信息面板。
- `AnalysisPage` 仍混合输入选择、结果视图、报告模板、保存结果目标推导和扩展面板编排。
- `ProcessPage` 仍混合多输入选择、pipeline 编排、保存计划、预览渲染和扩展配置。
- `SettingsPage`、`extension_options_form`、`import_dialog`、`export_flow` 仍是高复用但偏大的 UI surface。

## 实施顺序

1. 先按页面职责拆：
   - selection/input coordinator
   - save/export target coordinator
   - preview/result presenter
   - extension panel adapter
2. 再处理共享控件/对话框：
   - extension options form
   - import/export flow
   - image viewer supporting services
3. 最后统一跨页面约定：
   - 页面壳层只负责布局、状态桥接和顶层命令接线
   - support 模块负责具体业务交互细节

## 验收标准

- 页面级 bug 修复可以在局部 coordinator / presenter 中完成，而不是再次跨越整页。
- 保存/导出目标推导不再散落在多个页面私有方法里。
- 扩展面板与页面主流程的耦合进一步下降。

## 提交检查点

- 检查点 1：`DigitizePage` / `AnalysisPage` 深拆完成。
- 检查点 2：`ProcessPage` / `SettingsPage` 与共享控件/对话框深拆完成。
- 检查点 3：跨页面编排约定统一与窄测验收完成。

## 风险与回退

风险：

- 页面深拆若不保持现有状态桥接顺序，容易引入 focus、theme、preview 生命周期回归。
- 高复用对话框/控件改动面广，若缺少窄测会影响多个页面。

回退方式：

- 若某页面 support 抽取后仍需大量反向访问页面属性，回退该抽取并重新设计最小状态接口。
- 若共享控件拆分导致多个页面联动异常，先保留兼容适配层，再逐页切换消费者。

## 延后到后续阶段的问题

- 当本阶段完成后，才允许进入以功能优化为主的路线。
- 进入功能优化前，仍需完成 `Phase 37` 的结构闭环检查与质量门槛固化。
