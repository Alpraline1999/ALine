# Phase 15：超大页面与共享控件深拆

## 目标与完成定义

目标：

- 在 `Phase 14` 清掉高收益重复实现之后，继续处理剩余的超大页面与共享控件 monolith。
- 不再只做壳层收口，而是把高复杂度页面和共享 widget 真正拆成可维护的装配结构。
- 收口页面对 `workspace_state` 的大批量代理属性，让状态桥接从“页面类堆 setter/getter”转向受控 bridge / presenter。

完成定义：

- `DataPage`、`project_tree`、`image_viewer`、`extension_options_form` 至少完成一轮实质性拆分，不再继续作为默认 monolith 入口增长。
- `chart_page`、`analysis_page`、`process_page`、`digitize_page` 中高密度的 `workspace_state` 代理属性显著减少，公共模式被迁入受控桥接层。
- 页面与共享 widget 的职责界面更明确：
  - shell
  - state bridge
  - presenter
  - action coordinator
  - panel / widget module
- 后续新增功能不再默认落到 3000-5000 行的单文件中。

## 进入前提

- `Phase 14` 完成。
- extension runtime、ProjectManager 重复逻辑和 shared bootstrap 已经稳定，不再阻塞 UI 深拆。

## 本阶段纳入的状态与边界

- 纳入：
  - `ui/pages/data_page.py`
  - `ui/widgets/project_tree.py`
  - `ui/widgets/image_viewer.py`
  - `ui/widgets/extension_options_form.py`
  - `ui/pages/chart_page.py`
  - `ui/pages/analysis_page.py`
  - `ui/pages/process_page.py`
  - `ui/pages/digitize_page.py`
  - `ui/page_view_state.py`
  - 新增的 presenter / bindings / panel factory / action coordinator 模块
- 不纳入：
  - 新业务功能
  - 共享控件的视觉重设计
  - `core` / `processing` 算法大改
  - 扩展协议再次重构

## 本阶段禁止改动的区域

- 禁止为了拆文件而把业务状态散回 `MainWindow` 或随机 helper。
- 禁止把大型共享 widget 切成多个无主 util 文件。
- 禁止将 state proxy 问题通过继续追加 property 包装器解决。
- 禁止在 `DataPage` 边界未明时把其强行贴合其它页面的交互壳层。

## 目标接口/类型/运行时对象

- `DataPageViewState`
- `DataPageStateBridge`
- `ProjectTreePresenter`
- `ImageViewerOverlayController`
- `ExtensionOptionsFormPresenter`
- `PageStateBridge`
- `SelectionCoordinator`
- `PreviewPresenter`

## 实施顺序

1. 先处理最重的页面与 widget：
   - `DataPage`
   - `project_tree`
   - `extension_options_form`
   - `image_viewer`
2. 再收口各页面上的状态代理模式：
   - `chart_page`
   - `analysis_page`
   - `process_page`
   - `digitize_page`
3. 固定共享拆分约定：
   - bridge 只映射状态
   - presenter 只组织显示数据
   - coordinator 只处理用户动作流
4. 增加针对 shell / bridge / presenter 的窄测

## 核心问题清单

- `DataPage` 仍然是超大页面，同时存在重复状态初始化和大量节点路由/预览/导入管理逻辑混堆。
- `project_tree` 已成为共享控件级 monolith，承载排序、拖放、上下文菜单、批量路由和 tooltip 逻辑。
- `image_viewer` 混合了显示、交互、遮罩、校准、点编辑和工具模式。
- `extension_options_form` 继续承载大批量字段绑定、交互选择器和表单布局细节。
- 多个页面继续通过大批量 property 代理 `workspace_state`，导致边界噪声高、调试路径长。

## 子阶段建议

### 15.1 DataPage 深拆与状态桥接

目标：

- 把 `DataPage` 从“节点路由 + 预览 + 导入管理 + 全局扩展配置预览”的大杂糅结构拆成可维护模块。

纳入：

- 节点路由与右侧预览桥接
- 导入队列与待导入状态
- 全局扩展配置预览/编辑路由
- 页面状态 dataclass / bridge

验收要点：

- `DataPage` 不再重复初始化同一批状态。
- 页面构造期的状态字段和 UI 装配路径明显收短。

### 15.2 Shared Widget 深拆

目标：

- 把 `project_tree`、`image_viewer`、`extension_options_form` 变成职责明确的组合模块。

验收要点：

- 共享 widget 主文件显著缩短。
- 拖放、上下文菜单、overlay、字段绑定等逻辑有清晰归属。

### 15.3 Page State Proxy 收口

目标：

- 减少页面类中的 `return self._workspace_state.*` / setter 代理堆积。

验收要点：

- 至少一组页面改为 bridge / presenter 模式，不再继续追加 property 代理。

## 验收标准

- 至少 2 个超大页面/共享 widget 完成实质性深拆。
- `workspace_state` 代理属性模式开始实质性减少，而不是继续扩张。
- `DataPage` 的后续结构入口稳定，不再依赖错误前提。
- 新增窄测覆盖 bridge / presenter / coordinator，而不仅是黑盒 smoke。

## 提交检查点

- 检查点 1：`DataPage` 前半拆分与 state bridge 落地。
- 检查点 2：`project_tree` / `extension_options_form` 首批深拆完成。
- 检查点 3：`image_viewer` 或页面 state proxy 收口完成。
- 检查点 4：阶段验收与结构 guardrails 完成。

## 风险与回退办法

风险：

- 页面/共享 widget 深拆时把交互回调链打散。
- state bridge 抽象过重，导致阅读成本更高。

回退办法：

- 若某次深拆只带来文件数量上升而边界更差，则回退该次拆分。
- 若 bridge/presenter 设计过重，收缩为最小职责接口后再继续。

## 延后到后续阶段的问题

- 静态风格债务系统清理
- 静默异常策略统一
- 分析/导入等长流程模块的大型编排重构
