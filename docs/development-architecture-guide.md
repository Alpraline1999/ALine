# ALine 重构后软件开发架构指南

## 1. 文档目的

本指南是 ALine 在重构阶段结束后，进入持续开发、功能优化与长期维护阶段的统一开发约束文档。

它的目标不是解释“历史上做过什么重构”，而是明确：

- 当前代码库的真实分层、职责边界和依赖方向
- 后续功能开发应该落在哪一层、以什么模式实现
- 哪些做法被允许，哪些做法会破坏一致性、可维护性和性能
- 代码评审、测试、文档更新和结构审查应如何执行

本指南应作为后续开发的长期基线。任何会改变分层边界、模块职责、状态归属、扩展协议或质量门禁的改动，都必须同步更新本文件。

## 2. 适用范围与上位文档

本指南适用于：

- 新功能开发
- 现有功能扩展
- 缺陷修复
- 性能优化
- UI 调整
- 扩展开发
- AI 能力接入
- 测试和维护性改造

与本指南直接相关的上位或配套文档如下：

- `docs/refactor/README.md`
  - 记录 Phase 0-37 的重构路线、进入/退出规则与收尾结论。
- `docs/feature-optimization/README.md`
  - 记录重构完成后进入功能优化阶段的规划入口。
- `scripts/structure_check.py`
  - 结构门禁脚本，负责大文件预算、私有 API 泄漏、命令面重复等检查。
- `tests/test_architecture_guardrails.py`
  - 架构护栏测试，冻结 UI 直连 runtime import、core 直连 `extensions.*`、MainWindow 私有页面访问等规则。
- `tests/test_refactor_guardrails.py`
  - 重构期护栏集合入口。

优先级规则：

1. 若本指南与实际代码冲突，以“当前代码 + 已存在测试护栏”为准，并立即修正文档。
2. 若新改动准备突破当前边界，必须先明确修改护栏与文档，再改实现。
3. 不允许只改代码不更新架构文档与护栏。

## 3. 当前架构总览

当前 ALine 的主分层如下：

| 层 | 目录 | 主要职责 |
|---|---|---|
| 领域模型层 | `models/` | 项目、数据、图片、分析、模板、AI 资源等共享 schema |
| 核心运行时层 | `core/` | 项目存储、迁移、全局资产、扩展协议、数值数据适配、分析/渲染等核心能力 |
| 应用编排层 | `app/` | 页面与核心之间的业务态、树命令服务、工作区状态控制器、消息对象 |
| AI 编排层 | `ai/` | AI 命令注册、命令分发、技能运行、Agent 主循环 |
| UI 层 | `ui/` | 主窗口、页面、对话框、控件、主题和交互装配 |
| 处理算法层 | `processing/` | 通用处理算法、数据处理 pipeline、与扩展共享的处理基础 |
| 扩展层 | `extensions/` | 内置 processing / analysis / plot / digitize 扩展实现 |
| 测试与门禁 | `tests/`, `scripts/` | 目标性窄测、架构护栏、结构检查 |

整体依赖方向应保持为：

`ui -> app -> core -> models`

并辅以：

- `ui -> core`
  - 仅允许少量受控的运行时单例直连，且必须受护栏测试约束。
- `ai -> core`
  - 允许，因为 AI 命令本质是对核心能力的外部编排接口。
- `extensions -> core / processing / models`
  - 允许，扩展属于能力实现层。

禁止方向：

- `core -> ui`
- `models -> core/ui/app`
- `core -> extensions.*` 直接硬编码依赖
- `app -> ui` 的细粒度控件依赖
- `ui` 跨模块访问 `project_manager._*`

## 4. 目录职责与开发落点

### 4.1 `models/`

`models/schemas.py` 是项目持久化模型与跨层共享数据结构的唯一源。

适合放在这里的内容：

- 项目文件内需要保存的结构
- 页面/核心/扩展共享的数据实体
- 需要迁移兼容的结构化模型

不适合放在这里的内容：

- Qt 对象
- 业务流程控制器
- 扩展调用逻辑
- 与磁盘路径、UI 组件绑定过深的运行时状态

规则：

- 新增持久化字段时，必须考虑旧项目兼容与迁移。
- 影响 `.aline` 持久化结构的修改，必须同步检查 `core/project_repository.py`、`core/project_migration_service.py`、`core/project_manager.py` 以及相关测试。

### 4.2 `core/`

`core/` 是项目核心能力层，负责“可复用、可脱离 UI 运行”的业务与基础设施。

当前关键模块：

- `core/project_manager.py`
  - 项目读写、树节点管理、数据/图片/分析/模板对象的 façade 入口
- `core/project_services.py`
  - `ProjectManager` 所依赖的 service 组装
- `core/project_repository.py`
  - 项目持久化读写
- `core/project_migration_service.py`
  - 版本迁移
- `core/project_tree_service.py`
  - 项目树相关领域能力
- `core/project_asset_service.py`
  - 项目内资产处理
- `core/project_session.py`
  - 对当前项目会话访问的轻量 façade
- `core/global_assets.py`
  - 全局模板、主题、扩展配置、AI prompt/skill/agent 的存储与操作入口
- `core/extension_api.py`
  - 现阶段扩展集成入口与兼容层
- `core/extension_runtime.py`
  - 扩展执行请求/结果与运行时调用 façade
- `core/extension_types.py`
  - 扩展共享上下文与 patch/type helper
- `core/curve_data.py`
  - 曲线运行时数组主表示
- `core/line_tools.py`
  - line 协议兼容层与曲线转换工具
- `core/rendering.py`
  - 绘图抽样/渲染性能相关基础能力

规则：

- 新的“可被多个页面、扩展或命令复用”的能力，优先进入 `core/`。
- `core/` 中可以有 façade，但 façade 不应继续无约束膨胀；复杂逻辑优先拆到 service/helper。
- `core/` 不得依赖 Qt widget、页面类或对话框。
- `core/` 不得直接 import `extensions.*`。扩展发现和运行必须走 registry / loader / runtime。

### 4.3 `app/`

`app/` 是 UI 与 core 之间的应用编排层，负责“页面交互过程中的业务态和命令协作”，不是领域模型层，也不是 Qt 组件层。

当前关键模式：

- `app/workspaces/*.py`
  - 每个工作台页面对应一个 `*WorkspaceState` 与 `*WorkspaceController`
- `app/project_tree_command_service.py`
  - 项目树右键命令与批处理动作的服务面
- `app/messages.py`
  - `AppCommand` / `TreeCommand` / `SessionEvent` 等消息对象
- `app/tree_action_dispatcher.py`
  - 项目树事件到应用命令的分发
- `app/context.py`
  - 当前项目会话、全局资产、扩展运行时、事件总线等顶层上下文

规则：

- 页面中的“选择了什么、当前工作集是什么、树节点激活后应做什么”之类业务态，应优先进入 workspace state/controller。
- `app/` 可以依赖 `core/` 和 `models/`，但不应依赖具体页面组件。
- 需要给多个页面复用的业务编排，应先考虑放 `app/`，不要在页面文件里复制一份。

### 4.4 `ai/`

`ai/` 是独立于普通 UI 的命令编排层。

当前关键规则：

- `ai/command_registry.py`
  - 内置 AI 命令定义的唯一源
- `ai/command_layer.py`
  - `CommandDispatcher`，负责统一调度 registry 中的命令以及全局动态工具
- `ai/agent.py`
  - AI 对话主循环

新增 AI 命令时：

- 只在 `ai/command_registry.py` 注册
- 不在 `ai/command_layer.py` 再复制一套定义
- 若命令只是 core 能力的 AI 包装，优先调用已有 core façade，不在 AI 层重复业务实现

### 4.5 `ui/`

`ui/` 负责页面、窗口、控件和交互装配。

当前关键子层：

- `ui/main_window.py`
  - 主窗口、导航、共享项目树、页面装配
- `ui/tree_command_route.py`
  - 主窗口中的树命令路由收口点
- `ui/page_view_state.py`
  - 纯 UI 视图态定义
- `ui/theme.py`
  - 颜色 token、文本样式、卡片样式、统一 UI helper
- `ui/pages/`
  - 工作台页面与 support/bridge/helper 模块
- `ui/widgets/`
  - 共享控件和项目树子模块
- `ui/dialogs/`
  - 对话框和导出/导入流程

规则：

- `ui/` 只处理显示、交互和页面装配，不持有核心业务真相。
- UI-only 状态放 `ui/page_view_state.py` 或页面 bridge，不放进 `models/` 或 `core/`。
- 新功能不要继续把大型页面做成单文件膨胀，优先新增 support/helper/bridge/widget。

### 4.6 `processing/` 与 `extensions/`

`processing/` 是内建、通用、非 UI 的处理算法层。

`extensions/` 是按扩展协议对外暴露的可插拔实现层。

选择规则：

- 若能力是 ALine 内部稳定基础能力，应放 `processing/` 或 `core/`
- 若能力需要可启停、可配置、可被扩展面板管理，应放 `extensions/`
- 若多个扩展共用一段纯算法逻辑，应优先下沉到 `processing/` 或 `core/`，而不是在扩展文件间复制

## 5. 硬性依赖规则

### 5.1 UI 直连 core runtime 的允许边界

`tests/test_architecture_guardrails.py` 已冻结 UI 允许直连的 runtime import。

当前允许的受控单例直连主要只有：

- `core.project_manager.project_manager`
- `core.global_assets.global_assets`
- `core.extension_api.extension_registry`

结论：

- UI 新增对 core 的直接 import，默认视为不允许。
- 若确有必要，必须先证明无法通过 `app/`、page support、workspace controller 或 service façade 解决，再同步更新护栏测试。
- 不允许新增对 `project_manager._*` 私有方法的跨模块访问。

### 5.2 MainWindow 边界

`tests/test_architecture_guardrails.py` 当前冻结了：

- `ui/main_window.py` 不再直接访问页面私有属性

因此：

- `MainWindow` 只能通过公开方法、信号、路由对象或协议接口驱动页面
- 不允许重新出现 `self.chart_page._xxx` 这种调用

### 5.3 core 与 extensions 的方向

当前护栏冻结为：

- `core/` 不直接 import `extensions.*`

因此：

- 所有扩展发现、注册、调用都必须经过 `core.extension_api`、`core.extension_runtime`、loader/bootstrap 或 registry
- 不要在 core 里写死对某个内置扩展文件的依赖

## 6. 状态模型与所有权规则

ALine 当前已经明确区分四类状态：

### 6.1 持久化业务实体

位置：

- `models/schemas.py`
- 项目内对象由 `ProjectManager` / repository 管理
- 全局对象由 `global_assets` 管理

示例：

- `Project`
- `DataFile`
- `DataSeries`
- `ImageWork`
- `AnalysisResult`
- `FigureConfig`
- `PlotTheme`
- `ReportTemplate`

规则：

- 这类状态是真正的数据来源
- UI 只是读取、编辑、保存

### 6.2 页面业务运行时状态

位置：

- `app/workspaces/*.py`

示例：

- 图表工作集
- 当前选中的输入
- 处理页当前 pipeline 目标
- 分析页当前模板与选中树节点
- 数字化页当前图像、当前曲线、导出目标

规则：

- 与当前页面业务流程直接相关，但不一定持久化的状态，归 workspace state
- 页面类可以提供属性代理，但真实数据应落在 workspace state 中
- 页面复杂交互优先经 workspace controller 改 state，而不是分散在 widget callback 中直接修改一堆实例变量

### 6.3 纯 UI 视图态

位置：

- `ui/page_view_state.py`
- 各页面 bridge，如 `ui/pages/data_page_state_bridge.py`

示例：

- splitter 宽高
- 扩展面板显隐
- tooltip / browser / preview 的局部视图态
- 是否由用户手动拖动过 splitter

规则：

- 纯视觉态不进入 `ProjectManager`
- 纯视觉态不进入 `models`
- 纯视觉态不要伪装成业务数据

### 6.4 会话级上下文

位置：

- `app/context.py`
- `core/project_session.py`

规则：

- 会话级能力以 façade 形式暴露
- 页面需要的是“能力接口”，不是一组内部对象指针

## 7. 页面开发范式

### 7.1 标准页面形态

后续工作台页面应尽量遵循以下模式：

1. 页面主文件负责装配 Qt 组件与公开交互接口
2. 页面业务态进入 `app/workspaces/*`
3. 页面纯 UI 态进入 `ui/page_view_state.py` 或 page state bridge
4. 页面 support 模块承接常量、局部 widget/helper、matplotlib bootstrap、格式化函数
5. 跨页面复用逻辑提炼到 `ui/pages/page_shell_helpers.py`、共享 coordinator、共享 widget 或 `app/`

### 7.2 何时新增 support / bridge / widget

满足下列任一条件，优先提取：

- 同一页面中有一组常量、局部对话框、局部 helper 被反复使用
- 纯 UI 态代理属性已经明显膨胀
- 两个以上页面出现相似的 panel shell、导出协调或主题绑定逻辑
- 大页面新增逻辑会继续放大单文件复杂度

当前已存在的可复用模式：

- `ui/pages/page_shell_helpers.py`
- `ui/pages/save_export_coordinator.py`
- `ui/pages/*_support.py`
- `ui/pages/*_state_bridge.py`
- `ui/widgets/project_tree_delegate.py`
- `ui/widgets/project_tree_drag_drop.py`
- `ui/widgets/project_tree_menu_commands.py`

### 7.3 页面公开接口规则

页面对外公开的能力，必须通过显式方法暴露，例如：

- `on_tree_node_selected`
- `on_tree_node_activated`
- `receive_data`
- `load_template`
- `load_analysis_result`

禁止：

- 让外部模块直接读写页面私有控件或私有状态
- 在 `MainWindow`、树控件、对话框里直接依赖页面内部布局细节

## 8. 主窗口与项目树交互规则

当前树相关职责已被拆成多个面：

- `ui/widgets/project_tree.py`
  - 项目树控件主体
- `ui/widgets/project_tree_delegate.py`
  - 自定义 delegate / 绘制职责
- `ui/widgets/project_tree_drag_drop.py`
  - 拖放职责
- `ui/widgets/project_tree_menu_commands.py`
  - 菜单动作定义与拼装
- `app/project_tree_command_service.py`
  - 菜单命令对应的业务动作
- `app/tree_action_dispatcher.py`
  - tree 事件到 `AppCommand`
- `ui/tree_command_route.py`
  - 主窗口内树命令路由到页面/工作台

开发规则：

- 新的树右键功能，优先看它属于“菜单展示”、“命令服务”还是“主窗口路由”
- 新的树激活/选中行为，优先落到 `TreeCommandRoute`
- 新的批量删除、移动、导入之类树业务动作，优先放 `ProjectTreeCommandService`
- 树控件本身不应吞掉过多业务逻辑

简单判定：

- 只是右键菜单增加一个动作项：`project_tree_menu_commands.py`
- 动作需要弹窗、调用 `project_manager`、刷新树：`project_tree_command_service.py`
- 动作要切换页面或把树节点发送到某个工作台：`ui/tree_command_route.py`

## 9. ProjectManager 与持久化边界

### 9.1 ProjectManager 的角色

`core/project_manager.py` 当前仍是遗留大型 façade，但它的职责已经明确：

- 面向 UI / app / AI 暴露公开项目操作接口
- 组装 repository / migration / tree / asset / session services
- 维护 current project 概念

它不是：

- UI 状态存储区
- 扩展实现层
- 临时 helper 的堆放区

### 9.2 对 ProjectManager 的开发要求

- 只使用公开方法
- 不允许新增跨模块 `project_manager._*` 访问
- 新增功能前，优先检查是否已有 façade 可用
- 若需要新增能力，优先新增公开 façade，并尽量下沉复杂逻辑到 service/helper

### 9.3 何时修改 repository / migration / schemas

以下变更必须联动：

- 新增项目文件字段
- 修改节点结构
- 修改数据集、图像、分析结果、模板的持久化结构
- 兼容旧 `.pyline` / `.aline` 项目格式

最少需要检查：

- `models/schemas.py`
- `core/project_repository.py`
- `core/project_migration_service.py`
- `core/project_manager.py`
- 相关测试

## 10. GlobalAssets 与全局资源规则

`core/global_assets.py` 管理与项目无关、跨项目共享的资源：

- saved pipelines
- figure templates
- report templates
- curve style templates
- plot themes
- extension configs
- AI prompts / skills / agents

规则：

- 全局资源只能通过 `global_assets` 统一读写
- 不要在页面或对话框中直接读写 `~/.config/aline/global_assets.json`
- 任何新的“全局共享模板/配置/可复用资源”若不属于项目文件，应优先考虑接入 `global_assets`

命名建议：

- 项目级对象使用 `project_manager`
- 全局共享对象使用 `global_assets`
- 不要把全局资源又塞回项目文件，造成双真相

## 11. 扩展体系开发规范

### 11.1 扩展类别

当前支持四类扩展：

- `processing`
- `analysis`
- `plot`
- `digitize`

### 11.2 扩展入口与契约

涉及文件：

- `core/extension_api.py`
- `core/extension_runtime.py`
- `core/extension_types.py`
- `extensions/<category>/...`

扩展开发的原则：

- 扩展实现放在 `extensions/`
- 扩展运行时适配放在 `core/extension_*`
- 页面不直接实现扩展协议本身

### 11.3 line 协议与曲线数据

当前扩展协议仍大量使用 line 协议：

- `line = [[x, y], ...]`

但运行时主表示已经迁移到数组后端：

- `core.curve_data.CurveBuffer`
- `core.curve_data.SeriesArrayView`

因此：

- 新写核心热路径时，优先使用 `CurveBuffer` / 数组视图
- 面向扩展兼容输出时，再通过 `core.line_tools` 转换为 line
- 不要在热路径中频繁来回做 `list(point)`、`x/y list`、`numpy array` 的重复转换

### 11.4 plot 扩展样式 patch 规则

plot 扩展的上下文类型和 patch helper 已经在 `core/extension_types.py` 中统一：

- `PlotExtensionContext`
- `merge_nested_dict`
- `normalize_plot_extension_phases`

规则：

- 不要在每个 plot 扩展里发明新的样式合并协议
- 样式 patch、figure state patch、curve style patch 必须遵守统一上下文
- 若需要新增扩展 patch 能力，应先扩展共享上下文，再改页面应用逻辑

### 11.5 内置与外部扩展

扩展来源分为：

- `base`
- `builtin`
- `external`

规则：

- 所有扩展元信息都应走统一 version/source/tier 归一化逻辑
- 新的扩展兼容规则，不要散落在页面代码里
- settings 页只是展示和配置扩展，不定义扩展协议本身

## 12. AI 命令面规范

当前 AI 命令面已经做过去重，必须遵守：

- `ai/command_registry.py` 是内置命令定义唯一源
- `ai/command_layer.py` 只做 dispatcher 和动态 catalog
- 动态 prompt/skill/agent 来自 `global_assets`

新增 AI 能力时的落点：

- 新内置命令：`ai/command_registry.py`
- 新动态 AI 资源：`global_assets`
- 新 OpenAI 客户端交互能力：`core/ai_*` 或 `core/ai/`

禁止：

- 在 `command_layer.py` 与 `command_registry.py` 同时维护两份 command schema
- 在 AI 命令里重复实现已有 core 逻辑
- 在 UI 页面里复制一套 AI 执行入口

## 13. 大曲线与大数据量开发规则

这是后续功能优化阶段的重点，也是长期开发中最容易退化的区域。

### 13.1 当前基本原则

重构后的明确结论不是“把所有 list 全部替换成 numpy”，而是：

- 性能敏感的曲线主数据使用数组后端
- 兼容层通过 `CurveBuffer` / `SeriesArrayView` / `line_tools` 适配
- 非热点区域不强制全面 numpy 化

原因：

- 项目持久化模型、UI 表格、对话框输入、扩展兼容层仍有大量 list 语义
- 全量替换为 numpy 会扩大侵入面，增加序列化、兼容和 UI 接口成本
- 真正影响性能的是热路径中的复制、对齐、插值、重复转换和阻塞渲染

### 13.2 开发要求

- 热路径优先使用 `CurveBuffer`
- 只在边界层做必要转换
- 大批量曲线运算优先走共享 helper，不要在页面里手写循环复制
- 图表与预览渲染优先复用 decimation / virtualization 相关基础能力
- 避免在主题切换、页面刷新、树切换时无差别全量重绘全部大图

### 13.3 性能评审检查项

- 该改动是否引入新的全量复制
- 是否重复构造 `line` / `x,y list` / `numpy array`
- 是否把大运算放回 UI 主线程同步执行
- 是否影响主题切换、树切换、tab 切换的即时响应
- 是否能复用已有 `core/rendering.py`、`processing/` 或共享数值 helper

## 14. UI 主题、一致性与视觉约束

### 14.1 主题 token 唯一入口

`ui/theme.py` 是当前 UI 主题 token 和通用样式 helper 的统一入口。

优先使用：

- `text_color()`
- `secondary_color()`
- `placeholder_text_style_sheet()`
- `secondary_text_style_sheet()`
- `card_title_style_sheet()`
- `make_card_caption()`
- `make_hint_label()`
- `preview_canvas_background_color()` 等

禁止：

- 在页面中大面积硬编码浅色/深色颜色值
- 同类 label 在不同页面各自定义不同字号和灰度
- settings/card 描述性文案不经过统一样式 helper

### 14.2 页面壳层一致性

涉及卡片、说明 label、分隔、按钮尺寸等 UI 壳层规范时，应优先复用：

- `ui/theme.py`
- `ui/pages/page_shell_helpers.py`
- 已有 support 模块中的工厂函数

### 14.3 主题切换和自定义绘制

主题切换、delegate 绘制、eventFilter、自定义 showEvent / paintEvent 是高风险点。

要求：

- 修改自定义绘制或委托时，必须保证依赖 import 完整
- eventFilter 必须只做轻量判断，避免递归或重复触发链路
- 主题切换相关刷新应优先做局部更新，避免无差别全量重建
- 带 `QTimer.singleShot` 的延迟刷新必须考虑对象销毁期保护

## 15. 在遗留 monolith 中开发的规则

根据 `docs/refactor/README.md` 当前结论，以下文件仍属于遗留 monolith：

- `ui/pages/data_page.py`
- `ui/pages/chart_page.py`
- `ui/pages/digitize_page.py`
- `ui/pages/analysis_page.py`
- `ui/pages/settings_page.py`
- `core/project_manager.py`
- 大型测试文件 `tests/test_ui.py`、`tests/test_backend.py`

这不代表可以继续在其中无序叠加逻辑。

规则：

- 修改前先查找是否已有 support / bridge / helper / workspace / service 可承接
- 若新增逻辑超过一个清晰职责块，优先先提取新模块，再接线
- 不要在 monolith 里继续塞新的通用工具函数
- 不要为了少建一个文件，把跨页面复用逻辑复制进两个大页面

判断标准：

- 如果新逻辑未来可能被第二个页面复用，应立即提取
- 如果新逻辑与当前页面的 widget 装配无强绑定，不应留在页面主文件

## 16. 测试、结构检查与验证要求

### 16.1 默认验证策略

默认使用目标性窄测，不做无差别全量回归。

推荐验证顺序：

1. 改动模块的直接单测
2. 相关护栏测试
3. 必要时运行 `scripts/structure_check.py`
4. 必要时补一个最小 smoke test

### 16.2 必跑门禁

涉及架构边界调整时，至少检查：

- `tests/test_architecture_guardrails.py`
- `tests/test_refactor_guardrails.py`
- `scripts/structure_check.py`

涉及页面壳层、共享 helper、support 模块时，优先检查：

- `tests/test_page_shell_helpers.py`
- `tests/test_page_support_modules.py`

### 16.3 新测试编写规则

- 优先补目标模块测试，不往 `tests/test_ui.py` 继续堆
- 页面测试尽量按 `tests/pages/`、`tests/widgets/`、`tests/dialogs/` 归类
- 架构规则若被新约束固化，必须有对应护栏测试

## 17. 文档与变更管理要求

以下情况必须更新文档：

- 新增或调整层级边界
- 改变 UI 对 core 的允许直连规则
- 调整扩展协议
- 引入新的全局资源类别
- 修改大曲线/数组主表示策略
- 调整结构门禁或大文件预算
- 新增功能优化阶段的重要前置约束

文档更新位置按内容选择：

- 架构长期规则：本指南
- 重构/结构阶段性约束：`docs/refactor/`
- 功能优化阶段方案：`docs/feature-optimization/`

## 18. 新功能开发落点速查

| 需求类型 | 首选落点 |
|---|---|
| 新的项目持久化字段或节点结构 | `models/schemas.py` + `core/project_repository.py` + migration/service |
| 新的项目级业务操作 | `core/project_manager.py` façade，复杂部分下沉到 service/helper |
| 新的页面业务运行时状态 | `app/workspaces/*.py` |
| 新的纯 UI 视图状态 | `ui/page_view_state.py` 或 page state bridge |
| 新的项目树批量命令/菜单行为 | `app/project_tree_command_service.py` / `ui/widgets/project_tree_menu_commands.py` |
| 新的树选中/激活页面路由 | `ui/tree_command_route.py` |
| 新的全局模板/共享配置 | `core/global_assets.py` |
| 新的处理算法基础能力 | `processing/` 或 `core/` |
| 新的扩展实现 | `extensions/<category>/` |
| 新的扩展运行时契约 | `core/extension_runtime.py` / `core/extension_types.py` / `core/extension_api.py` |
| 新的 AI 内置命令 | `ai/command_registry.py` |
| 新的主题 token / 统一样式 helper | `ui/theme.py` |

## 19. 代码评审检查清单

提交代码前，至少自查以下问题：

- 是否把功能放在了正确层级，而不是图省事塞进页面或主窗口
- 是否新增了 UI 对 core 的非受控直接依赖
- 是否重新引入了 `project_manager._*` 私有访问
- 是否在大曲线热路径中增加了重复转换或全量复制
- 是否把纯 UI 状态和业务状态混在一起
- 是否复用了已有 theme token、page shell helper、save/export coordinator、workspace controller
- 是否把新测试继续堆进超大旧测试文件
- 是否需要更新护栏测试、结构检查或本指南

## 20. 长期维护原则

后续开发必须坚持以下原则：

- 先找现有边界，再写代码，不允许边界失守后再补救
- 先抽离职责，再给遗留 monolith 继续加功能
- 先优化热路径，再讨论是否扩大 numpy 化范围
- 先统一共享契约，再让页面、扩展、AI 各自发明一套协议
- 先补目标性护栏，再相信“以后不会再长回去”

本指南的最终目标不是让目录看起来漂亮，而是确保 ALine 后续每一轮功能开发都能在一致、可维护、可扩展、可验证的结构内进行。
