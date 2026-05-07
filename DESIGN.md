# ALine 软件设计与结构文档

> 状态：当前实现基线
> 适用范围：仓库主干、后续功能开发、缺陷修复、结构演进
> 关联文档：
> `README.md`
> `docs/development-architecture-guide.md`
> `docs/refactor/README.md`
> `docs/feature-optimization/README.md`

## 1. 文档目的

本文件是 ALine 当前版本的统一软件设计与结构说明。

它不再记录历史阶段计划，也不再区分“设计文档”和“下一阶段规划文档”。它只回答四个问题：

1. ALine 当前解决什么问题。
2. 当前代码库按什么架构分层组织。
3. 关键运行流、数据模型、扩展协议如何协作。
4. 仓库中哪些目录和文档是长期维护入口。

如果当前实现与本文冲突，以“当前代码 + 测试护栏 + `docs/development-architecture-guide.md`”为准，并同步修正文档。

## 2. 产品定位

ALine 是一个面向科研与工程场景的桌面数据工作台，用于把图片中的曲线数字化、把曲线资产组织进项目、执行处理与分析、生成图表与报告素材，并通过 Python 扩展接入领域算法。

它不是单一“取点工具”，也不是单一“绘图工具”。当前产品核心是一个项目驱动的数据工作流：

1. 导入图片或数据文件。
2. 在共享项目树中组织数据、图片、分析结果、模板和扩展配置。
3. 在数字化、数据处理、数据分析、可视化页面之间共享资产，而不是在每个页面复制一套数据源。
4. 使用模板、全局资源和扩展机制复用流程。

当前主工作流包括：

- 图片数字化到数据列
- 原始曲线到处理流水线
- 曲线到分析结果与报告模板
- 曲线到最终图表与图片导出
- 内置/外部扩展加载、配置、应用与重载

## 3. 当前架构总览

ALine 当前遵循以 `models -> core -> app -> ui` 为主干的分层架构。

| 层 | 目录 | 职责 |
| --- | --- | --- |
| 领域模型层 | `models/` | 项目、数据、图片、模板、分析结果、绘图快照等共享 schema |
| 核心运行时层 | `core/` | 项目持久化、迁移、全局资产、扩展协议、扩展运行时、导出、渲染、偏好设置 |
| 应用编排层 | `app/` | 页面工作区状态、树命令服务、消息对象、上下文与业务编排 |
| UI 层 | `ui/` | 主窗口、页面、对话框、共享控件、主题与交互装配 |
| 处理与算法层 | `processing/`, `digitize/` | 曲线处理、校准、图像提取等可复用基础算法 |
| 扩展实现层 | `extensions/` | processing / analysis / plot / digitize 四类内置扩展 |
| AI 运行时层 | `ai/`, `core/ai/` | 命令注册、工具分发、Agent 运行时与 provider 封装 |
| 测试与门禁 | `tests/`, `scripts/` | UI/后端回归、架构护栏、结构检查 |

主依赖方向保持为：

`ui -> app -> core -> models`

辅助方向：

- `ui -> core`
  当前保留少量受控单例直连，如 `project_manager`、`global_assets`、`extension_registry`。
- `extensions -> core / processing / models`
  扩展属于能力实现层，可以依赖稳定协议与基础算法。
- `ai -> core`
  AI 命令本质上是对核心能力的编排入口。

明确禁止：

- `core -> ui`
- `models -> core/ui/app`
- `core` 直接硬编码依赖 `extensions.*`
- 页面跨模块调用 `project_manager._*` 私有方法

更严格的边界约束以 [docs/development-architecture-guide.md](/home/alpraline/Projects/Python/ALine/docs/development-architecture-guide.md) 为准。

## 4. 主窗口与页面结构

应用入口为 [main.py](/home/alpraline/Projects/Python/ALine/main.py)，主窗口为 [ui/main_window.py](/home/alpraline/Projects/Python/ALine/ui/main_window.py) 中的 `MainWindow`。

当前页面集合：

- 首页 `HomePage`
- 数据管理页 `DataPage`
- 可视化页 `ChartPage`
- 数据处理页 `ProcessPage`
- 数据分析页 `AnalysisPage`
- 图片数字化页 `DigitizePage`
- 设置页 `SettingsPage`

除首页和设置页外，主窗口使用“导航栏 + 共享项目树 + 当前工作区”的工作台布局。共享项目树是页面 2-6 的统一资产入口。

主窗口关键协作对象：

- `ProjectTreeWidget`
  负责项目树渲染、拖拽、右键菜单、专注模式和节点管理。
- `TreeCommandRoute`
  将树节点动作路由到数据、图表、处理、分析、数字化页面。
- `ProjectTreeActionDispatcher`
  负责树级应用命令的分发。
- `AppContext`
  持有全局上下文与可共享运行时资源。

页面内部不再维护第二套全量源树。页面只维护“当前工作集”，例如：

- 图表页的当前曲线工作集
- 处理页的当前输入与 Pipeline
- 分析页的当前输入与结果上下文
- 数字化页的当前图片、曲线、校准与导出目标

## 5. 工作区状态模型

当前各工作台页面都引入了 workspace state/controller：

- [app/workspaces/data_workspace.py](/home/alpraline/Projects/Python/ALine/app/workspaces/data_workspace.py)
- [app/workspaces/chart_workspace.py](/home/alpraline/Projects/Python/ALine/app/workspaces/chart_workspace.py)
- [app/workspaces/process_workspace.py](/home/alpraline/Projects/Python/ALine/app/workspaces/process_workspace.py)
- [app/workspaces/analysis_workspace.py](/home/alpraline/Projects/Python/ALine/app/workspaces/analysis_workspace.py)
- [app/workspaces/digitize_workspace.py](/home/alpraline/Projects/Python/ALine/app/workspaces/digitize_workspace.py)

这些模块负责：

- 页面级业务真相
- 树节点选中/激活后的状态迁移
- 当前工作集与 UI 控件之间的业务态同步

`ui/page_view_state.py` 中的 view state 只保存纯 UI 视图态，例如 tooltip、面板显隐、局部显示状态，不保存领域真相。

## 6. 项目、资产与持久化模型

### 6.1 项目模型

项目持久化模型位于 [models/schemas.py](/home/alpraline/Projects/Python/ALine/models/schemas.py)。

这里定义了：

- 项目对象
- 文件夹和树节点
- 数据文件与数据列
- 图片与数字化结果
- 分析结果与报告模板
- 绘图样式、曲线样式、绘图快照
- 扩展配置与 AI 相关资源

### 6.2 项目持久化与迁移

项目相关核心服务集中在 `core/`：

- [core/project_manager.py](/home/alpraline/Projects/Python/ALine/core/project_manager.py)
  当前项目 façade 与高层能力入口
- [core/project_repository.py](/home/alpraline/Projects/Python/ALine/core/project_repository.py)
  项目读写
- [core/project_migration_service.py](/home/alpraline/Projects/Python/ALine/core/project_migration_service.py)
  旧版本迁移
- [core/project_tree_service.py](/home/alpraline/Projects/Python/ALine/core/project_tree_service.py)
  树节点与分组能力
- [core/project_asset_service.py](/home/alpraline/Projects/Python/ALine/core/project_asset_service.py)
  项目资产级操作
- [core/project_session.py](/home/alpraline/Projects/Python/ALine/core/project_session.py)
  当前项目会话访问

### 6.3 共享项目树语义

项目树当前用于组织以下资产：

- 普通文件夹
- 数据文件、源文件、图片、图片结果
- 分析结果
- 全局 Pipeline 模板
- 全局报告模板
- 全局曲线样式模板
- 全局绘图样式/主题
- 全局扩展配置

树中的一些叶节点是运行时虚拟节点，例如 `series`、`curve`。它们在 UI 中可见、可选、可拖拽、可批处理，但其真实数据仍存储在父级资产对象中。

## 7. 全局资源与模板体系

全局资源统一由 [core/global_assets.py](/home/alpraline/Projects/Python/ALine/core/global_assets.py) 管理。

当前纳入统一管理的全局资源包括：

- Pipeline 模板
- 报告模板
- 曲线样式模板
- 绘图样式模板
- 绘图主题
- 扩展配置 preset
- AI Prompt / Skill / Agent 资源

这套体系的核心原则是：

1. 项目内资产和全局模板分离。
2. 设置页负责全局配置入口。
3. 页面内允许查看、编辑、保存和覆盖与自身工作流相关的模板。

例如：

- 处理页维护 Pipeline 模板
- 分析页维护报告模板与分析结果
- 图表页维护曲线样式、绘图样式、绘图扩展实例
- 数据页承担更通用的模板/配置编辑入口

## 8. 曲线数据与渲染协议

### 8.1 运行时曲线主表示

当前代码库在热点路径使用两套受控表示：

- 项目存储层与多数页面业务层仍使用结构化数据对象
- 数值与热路径通过 [core/curve_data.py](/home/alpraline/Projects/Python/ALine/core/curve_data.py)、[core/line_tools.py](/home/alpraline/Projects/Python/ALine/core/line_tools.py) 和 `processing/extension_tools.py` 做统一适配

### 8.2 扩展边界协议

扩展正式曲线协议使用 point-list：

```python
line = [[x0, y0], [x1, y1], ...]
lines = [line, ...]
```

扩展层的正式转换入口：

```python
from extensions.processing.extension_tools import line_from_xy, line_xy
```

仓库内部仍保留 `processing.extension_tools` 兼容转发层，但新的扩展实现应优先使用正式路径。

这条协议用于减少处理、分析、绘图、数字化四类扩展之间的结构漂移。

### 8.3 大曲线与绘图优化

当前大曲线优化以局部热路径收口为主，而不是全仓强制数组化。

相关模块：

- [core/rendering.py](/home/alpraline/Projects/Python/ALine/core/rendering.py)
  负责降采样、渲染辅助与大曲线预览优化
- [core/exporter.py](/home/alpraline/Projects/Python/ALine/core/exporter.py)
  负责大数据导出
- [ui/widgets/matplotlib_preview.py](/home/alpraline/Projects/Python/ALine/ui/widgets/matplotlib_preview.py)
  负责共享预览工具栏与交互契约

## 9. 扩展系统设计

### 9.1 当前扩展类型

扩展协议与注册表定义位于 [core/extension_api.py](/home/alpraline/Projects/Python/ALine/core/extension_api.py)。

当前主要扩展类型：

| 类型 | 用途 | 标准签名 | 返回值 |
| --- | --- | --- | --- |
| ProcessingExtension | 曲线处理 | `(lines, params)` | `line` |
| AnalysisExtension | 结果分析 | `(lines, params)` | `dict` |
| PlotExtension | 图表叠加或样式 patch | `(plot_context, params)` | `None` |
| DigitizeExtension | 图像提取曲线 | `(figure, params)` | `line` |

此外还有：

- `PlotStyleExtension`
- `CurveStyleExtension`

其中 `PlotExtension` 还带有 `phases`、`style_authority`、`authoritative_fields` 等绘图阶段和样式覆盖语义；图表页通过 `PlotExtensionContext` 驱动其执行，而不是直接把 `lines` 传给 handler。

`PlotStyleExtension` 与 `CurveStyleExtension` 用于图表页的样式 patch 与样式体系扩展。

### 9.2 扩展加载与运行时

关键模块：

- [core/extension_api.py](/home/alpraline/Projects/Python/ALine/core/extension_api.py)
  协议、registry、兼容入口
- [core/extension_loader.py](/home/alpraline/Projects/Python/ALine/core/extension_loader.py)
  扩展扫描与加载
- [core/extension_runtime.py](/home/alpraline/Projects/Python/ALine/core/extension_runtime.py)
  统一运行时调用 façade
- [core/extension_settings.py](/home/alpraline/Projects/Python/ALine/core/extension_settings.py)
  启停状态和来源设置

内置扩展位于：

- `extensions/processing/`
- `extensions/analysis/`
- `extensions/plot/`
- `extensions/digitize/`

对外说明文档位于 [extensions/README.md](/home/alpraline/Projects/Python/ALine/extensions/README.md)。

### 9.3 扩展配置 UI

当前扩展配置 UI 基础设施包括：

- [ui/widgets/extension_panel.py](/home/alpraline/Projects/Python/ALine/ui/widgets/extension_panel.py)
  页面级扩展面板
- [ui/widgets/extension_options_form.py](/home/alpraline/Projects/Python/ALine/ui/widgets/extension_options_form.py)
  字段驱动的参数表单
- [ui/dialogs/plot_extension_instance_dialog.py](/home/alpraline/Projects/Python/ALine/ui/dialogs/plot_extension_instance_dialog.py)
  图表页已加载绘图扩展实例的编辑对话框

当前支持的关键能力：

- 扩展启停和重载
- 内置/外部来源区分
- 配置 preset 保存与覆盖
- 绘图扩展实例级编辑与刷新加载
- 统一 Fluent 风格 tooltip 和参数说明布局

## 10. AI 能力现状

AI 运行时仍保留在仓库中，但它不是当前主产品工作流的第一优先入口。

相关模块：

- `ai/`
  命令注册、调度与 Agent 主循环
- `core/ai/`
  provider、tool registry、tool executor 等底层运行时
- [core/ai_client.py](/home/alpraline/Projects/Python/ALine/core/ai_client.py)
  兼容型 AI 配置/访问入口

当前设计原则：

1. AI 作为可接入能力保留。
2. AI 不应绕过项目管理器直接修改项目数据。
3. AI 的新增功能应优先复用已有 core façade，而不是复制业务实现。

## 11. 当前目录结构

建议从以下目录理解仓库：

```text
ALine/
├─ main.py                    # 应用入口
├─ README.md                  # 项目首页文档
├─ DESIGN.md                  # 当前软件设计与结构文档
├─ app/                       # 应用编排层、workspace controller、命令服务
├─ core/                      # 核心运行时、项目系统、扩展系统、全局资产
├─ models/                    # 持久化与共享 schema
├─ ui/                        # 主窗口、页面、对话框、共享控件
├─ processing/                # 曲线处理与扩展共享工具
├─ digitize/                  # 数字化底层算法
├─ extensions/                # 内置扩展
├─ ai/                        # AI 命令编排层
├─ docs/                      # 架构、重构、优化文档
├─ tests/                     # UI、后端、架构护栏测试
└─ scripts/                   # 结构检查等开发脚本
```

其中最值得优先阅读的文件：

- [ui/main_window.py](/home/alpraline/Projects/Python/ALine/ui/main_window.py)
- [core/project_manager.py](/home/alpraline/Projects/Python/ALine/core/project_manager.py)
- [core/global_assets.py](/home/alpraline/Projects/Python/ALine/core/global_assets.py)
- [core/extension_api.py](/home/alpraline/Projects/Python/ALine/core/extension_api.py)
- [ui/widgets/project_tree.py](/home/alpraline/Projects/Python/ALine/ui/widgets/project_tree.py)
- [extensions/README.md](/home/alpraline/Projects/Python/ALine/extensions/README.md)

## 12. 文档体系

当前文档应按职责理解：

- [README.md](/home/alpraline/Projects/Python/ALine/README.md)
  项目首页、运行方式、功能概览、开发入口
- [DESIGN.md](/home/alpraline/Projects/Python/ALine/DESIGN.md)
  当前软件设计与仓库结构基线
- [docs/development-architecture-guide.md](/home/alpraline/Projects/Python/ALine/docs/development-architecture-guide.md)
  持续开发阶段的架构规则与边界约束
- [docs/refactor/README.md](/home/alpraline/Projects/Python/ALine/docs/refactor/README.md)
  重构阶段实施索引与历史路线
- [docs/feature-optimization/README.md](/home/alpraline/Projects/Python/ALine/docs/feature-optimization/README.md)
  功能优化阶段索引

## 13. 开发与维护原则

后续开发默认遵守以下原则：

1. 页面不新增第二套全量数据源。
2. 新的可复用业务能力优先下沉到 `core/` 或 `app/`。
3. 扩展协议、参数字段、预览工具栏、项目树行为优先复用共享实现。
4. 修改持久化结构时同步考虑迁移和护栏测试。
5. 若改动影响架构边界，必须同步更新 `docs/development-architecture-guide.md` 与相关测试。

## 14. 结论

当前 ALine 已从“页面各自维护流程”的形态，收口为“共享项目树 + workspace 状态 + core 统一运行时 + 扩展协议”的桌面数据工作台。

后续任何设计调整，都应围绕这条主线展开，而不是回到页面内重复堆业务、重复存状态或重复定义扩展契约。
