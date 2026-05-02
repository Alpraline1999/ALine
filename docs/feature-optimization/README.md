# ALine 功能优化文档索引

本目录用于承接重构完成后的功能优化阶段方案。这里的文档只定义功能问题、优化目标、阶段边界、验收口径与执行顺序，不直接进行代码实现。

## 阅读顺序

1. [00-feature-optimization-roadmap.md](00-feature-optimization-roadmap.md)
2. [01-phase-1-home-and-chart-ux-polish.md](01-phase-1-home-and-chart-ux-polish.md)
3. [02-phase-2-chart-style-authority-and-extension-contract.md](02-phase-2-chart-style-authority-and-extension-contract.md)
4. [03-phase-3-visualization-workflow-and-feedback-polish.md](03-phase-3-visualization-workflow-and-feedback-polish.md)
5. [04-phase-4-extension-protocol-and-registration-modernization.md](04-phase-4-extension-protocol-and-registration-modernization.md)
6. [05-phase-5-large-curve-async-and-progressive-workflow.md](05-phase-5-large-curve-async-and-progressive-workflow.md)
7. [06-phase-6-data-intake-preview-and-provenance.md](06-phase-6-data-intake-preview-and-provenance.md)
8. [07-phase-7-global-assets-and-template-workflow.md](07-phase-7-global-assets-and-template-workflow.md)
9. [08-phase-8-process-analysis-batch-and-traceability.md](08-phase-8-process-analysis-batch-and-traceability.md)
10. [09-phase-9-ai-module-deactivation-and-redesign-prep.md](09-phase-9-ai-module-deactivation-and-redesign-prep.md)
11. [10-phase-10-static-runtime-guardrails.md](10-phase-10-static-runtime-guardrails.md)
12. [11-phase-11-visualization-performance-and-large-modules.md](11-phase-11-visualization-performance-and-large-modules.md)
13. [12-phase-12-home-empty-state-and-entry-layout.md](12-phase-12-home-empty-state-and-entry-layout.md)
14. [13-phase-13-project-tree-dragdrop-regression-and-guardrails.md](13-phase-13-project-tree-dragdrop-regression-and-guardrails.md)

## 当前阶段定位

- 本轮文档属于“功能优化阶段规划”，不是重构阶段续写。
- 这里的阶段目标默认建立在 `docs/refactor/README.md` 当前记录的重构收尾状态之上。
- 已明确登记为遗留 monolith 的大文件，不再作为本轮方案文档的阻塞前提，但后续功能实现时不得让这些页面继续无序膨胀。

## 当前功能审查结论

- 主页 banner 已有亮色与暗色两套资源文件：
  - `assets/aline_home_background.png`
  - `assets/aline_home_background_dark.png`
- 当前主页 banner 仅加载亮色背景资源，主题差异主要依赖渐变遮罩补偿，未真正按主题切换背景图。
- 可视化页曲线列表已经具备：
  - 多选
  - 工具栏“隐藏/显示当前选中”
  - 右键“仅显示选中”
- 但右键菜单仍缺少显式的“隐藏已选中 / 显示已选中 / 全部显示”动作，批量可见性操作不完整。
- 可视化页绘图扩展与曲线样式/绘图样式之间已经有 patch + sequence 合并链路，但当前规则更偏实现细节，没有形成用户可理解、可控制的“样式优先级契约”。
- 当前扩展协议与注册方式对“内置扩展 + 严格内部协议”场景基本合理：
  - 四类扩展入口明确
  - `lines_number`、`config_fields`、`source_kind`、`tool_tier` 等元数据已收口
  - 加载时已有基础 contract validation 与 load report
- 但若后续继续强化外部扩展生态、长耗时任务、样式所有权和批处理能力，现有协议仍缺少：
  - API/兼容性版本声明
  - capability / authority 元数据
  - 更统一的注册数据模型
  - 对 warnings / progress / cancel / provenance 的正式承载
- 大曲线链路虽然已有 decimation 和局部优化，但图表、处理、分析页仍以同步执行为主，缺少统一的后台执行、进度反馈和取消机制。
- 数据导入、源文件预览、项目树右键导入、DataPage 导入与后续数据来源追踪仍是分散工作流，适合单独优化。
- `global_assets` 已承载 Pipeline、绘图主题、报告模板、曲线样式模板、扩展配置、AI 资源等多类全局资产，但当前管理入口仍偏 CRUD，缺少更完整的预览、复用、迁移和依赖提示。
- 处理页与分析页已经具备基本模板、保存和导出能力，但批量工作流、复跑、结果对比和可追溯性还没有形成统一体验。
- AI 模块当前处于“基础结构仍在、用户面已不稳定”的状态：
  - `ai.command_registry` 仍是现存单一命令源
  - `ai.command_layer` / `ai.agent` / settings 中的 AI 管理入口存在兼容漂移风险
  - 主窗口层已经不应继续在启动链路中硬依赖 AI 模块
- 本轮额外静态审查已确认，“重构后支撑模块拆分 + 页面壳层收口”之外，还存在一类需要单独治理的问题：
  - 漏导入或重命名残留导致的 `NameError` / `F821`
  - helper/support 模块抽出后，页面层保留了已失效的旧符号引用
  - 这类问题已经在 `project_manager.py`、`global_assets.py`、`settings_page.py`、`project_tree.py`、`project_tree_menu_commands.py` 等处出现，不属于单点偶发
- 当前剩余优化热点仍较明确：
  - `ui/pages/chart_page.py` 仍是大曲线与主题切换的主要性能瓶颈
  - `ui/pages/data_page.py`、`ui/pages/digitize_page.py`、`ui/pages/analysis_page.py`、`ui/pages/settings_page.py` 仍偏大，后续功能继续叠加时有再次失控风险
  - 仅依赖人工点击回归，已经不足以覆盖“重构后模块接口漂移”这类错误
- 新一轮问题核查又确认了两类尚未收口的优化项：
  - 首页最近项目为空时，按钮区/最近项目标题/空状态提示仍沿用“列表填充剩余高度”的布局策略，页面不够靠上紧凑
  - 项目树拖放 helper 在拆分后残留旧私有方法名 `_drag_source_item_for_drop`，导致节点拖拽移动在运行时直接报错
- 鉴于后续可能完全重做 AI 模块，现阶段更合理的策略是：
  - 先把 AI 从主启动链路和日常用户路径中彻底解耦/禁用
  - 再单独规划新的 AI 架构、命令模型与 UI 交互面

## 使用方式

- 若后续进入功能实现，建议像重构阶段一样按 phase 顺序执行。
- 每个功能 phase 开始前，再单独生成对应任务计划文档。
- 本目录当前只提供方案，不要求现在落任务文档或提交实现。
