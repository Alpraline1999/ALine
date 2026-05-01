# Phase 27：UI 主题链路、绘制委托与回归审计

## 目标与完成定义

目标：

- 针对 `Phase 23` 到 `Phase 26` 期间暴露出的 UI late-stage 回归，建立一套可重复执行的全面检查方法，而不是继续依赖零散人工点击。
- 系统化审计主题切换链路、页面局部主题刷新、自定义绘制/委托运行时安全和 settings 文案颜色一致性。
- 把“theme switch 卡顿、delegate paint 缺依赖、局部 label 颜色不更新”这类问题收口为一组可执行的检查矩阵和窄测护栏。

完成定义：

- 存在一套明确的 UI 审计矩阵，覆盖以下问题族：
  - 主题切换主链路的同步阻塞与重绘放大
  - 自定义 `paint` / `drawBranches` / delegate / `showEvent` / `eventFilter` 的运行时安全
  - `SettingsPage` 与共享 widget 的主题文案、标题和辅助文本颜色一致性
- 至少一组 theme switch 性能样本、至少一组 custom paint/runtime smoke、至少一组 settings theme consistency 窄测被固定。
- 页面主题更新接口不再以“每页各自猜测该刷新什么”的方式漂移，最少要形成可审计的统一约定。

## 进入前提

- `Phase 26` 已完成项目树与页面交互 surface 的首轮收口。
- 以 `2026-05-01` 的实际运行时问题进入本阶段：
  - 切换主题颜色仍然出现明显卡顿。
  - 项目树长名称自动换行路径在自定义 delegate `paint()` 中触发 `QPainter` 未导入的运行时错误。
  - `SettingsPage` 中“项目树页面专注模式”“内置扩展”“启用内置扩展”“外部扩展”“启用外部扩展”“其他设置”等文案颜色未随主题统一变化。

## 本阶段纳入的状态与边界

- 纳入：
  - `MainWindow._on_theme_changed()` 到各页 `update_theme()` / `update_theme_colors()` 的主题传播链路
  - `SettingsPage` 标题、分组、辅助文本、卡片标题和局部自定义 label 的主题样式刷新
  - `ProjectTreeWidget` 及其 delegate / builder / support 的换行、绘制与尺寸 hint 路径
  - 所有在 `ui/widgets`、`ui/pages` 中自定义的 `paintEvent` / `paint` / `drawBranches` / `eventFilter` / `showEvent`
- 不纳入：
  - 新一轮视觉改版
  - 与主题无关的业务功能开发
  - 无证据的大范围重构或一次性全仓 UI 重写

## 本阶段禁止改动的区域

- 禁止把“全面检查”扩张成新的 UI 设计改版。
- 禁止为了消除个别卡顿，回退已经建立的 workspace state 或页面边界。
- 禁止没有样本和窄测就继续修改 `paint`、delegate、`eventFilter` 和主题调度链路。
- 禁止把所有 label 样式都改为手写字符串而绕过共享 theme helper。

## 目标接口/类型/运行时对象

- `MainWindow._on_theme_changed`
- `SettingsPage.update_theme_colors`
- `ProjectTreeWidget`
- `_ProjectTreeWrapAnywhereDelegate`
- `ClickAwayFocusCommitFilter`
- 页面级 `update_theme()` / `update_theme_colors()` 接口

## 全面检查方法

### 1. Theme Switch 链路盘点

目标：

- 画出主题切换的真实调用链，明确每个页面在主题变化时会做什么。

执行要求：

- 列出 `MainWindow` 调用的所有主题刷新入口。
- 记录每个页面在主题变化时执行的是：
  - 仅样式刷新
  - 轻量背景刷新
  - 延后重绘
  - 同步重绘
- 标记隐藏页面和可见页面是否共用同一路径。

验收要点：

- 每个页面的主题刷新责任明确可查。
- 不再依赖“猜测哪个页面会同步重绘”。

### 2. Theme Performance 样本固定

目标：

- 用窄范围样本而不是主观感觉判断主题切换是否卡顿。

执行要求：

- 对 `MainWindow._update_all_pages_theme()` 建立主线程耗时样本。
- 对 `chart/data/process/analysis/settings` 五类页面分别记录：
  - 主题切换调用次数
  - 同步重绘次数
  - 延后刷新是否在事件循环中批处理
- 固定至少两个场景：
  - 工作区空载
  - 含图表/预览/树换行的中等负载

验收要点：

- 存在可重复的 theme switch 耗时基线。
- 可区分“样式更新慢”还是“重绘链路过重”。

### 3. Custom Paint / Delegate Runtime Audit

目标：

- 系统性排查自定义绘制路径中的 import 漏项、非法状态假设和异常链伪装。

执行要求：

- 扫描以下 override：
  - `paintEvent`
  - `paint`
  - `drawBranches`
  - `eventFilter`
  - `showEvent`
- 对每个 override 检查：
  - 所用 Qt 类型是否已显式导入
  - 是否依赖可为空对象却未判空
  - 是否在事件链中触发新的同步 UI 操作
  - 是否可能把业务异常伪装成 `eventFilter` 或 `paint` 包装异常

验收要点：

- 自定义绘制与事件过滤路径存在一份集中清单。
- 至少一条项目树换行路径和一条事件过滤路径有稳定 smoke test。

### 4. Settings Theme Consistency Sweep

目标：

- 统一 `SettingsPage` 中标题、分组、卡片、辅助说明和局部自定义 label 的主题样式刷新。

执行要求：

- 列出所有通过手工 `setStyleSheet()` 设置颜色的 settings label。
- 区分以下几类文本：
  - 主标题
  - 分组标题
  - 卡片标题
  - 次级说明
  - 错误/提示文本
- 检查它们是否都在 `update_theme_colors()` 覆盖范围内。
- 对未纳入的 label，决定：
  - 改为共享 theme helper
  - 纳入统一刷新列表
  - 删除局部手写样式

验收要点：

- `SettingsPage` 不再依赖零散 `if hasattr(...)` 才能局部刷新颜色。
- 分组标题与卡片标题的主题变化路径一致。

### 5. UI 异常链排查规则固化

目标：

- 把这类 PySide/QFluentWidgets 多层异常链的定位方法固定下来。

执行要求：

- 在阶段文档或测试约定中明确：
  - 优先定位最底部第一条业务模块异常
  - 区分 `eventFilter` / `paint` / `drawBranches` 包装噪声与真实根因
  - 对 show/hide、delayed refresh、singleShot 路径优先补 smoke test

验收要点：

- 后续遇到类似长栈时，团队有统一定位策略，而不是逐层误判。

## 实施顺序

1. 盘点主题切换调用链和自定义绘制 override 清单。
2. 固定 theme switch 耗时样本和最小 smoke matrix。
3. 修复 `project_tree` 换行与 delegate 绘制路径的运行时安全问题。
4. 收口 `SettingsPage` 的主题颜色刷新面。
5. 为 theme switch、delegate paint 和 settings label 补 guardrail tests。

## 核心问题清单

- 主题切换现在仍可能触发多页同步重绘，`singleShot(0)` 只改变调度时机，不等于自动降低重绘成本。
- 项目树长名称换行依赖自定义 delegate 绘制，一旦 Qt 类型导入或文本绘制前提不完整，就会在 `paint()` 链路中直接炸运行时。
- `SettingsPage` 当前主题刷新覆盖的是部分已登记 label，而不是完整的文本样式面，导致分组标题和局部自定义说明容易漏刷。
- Qt 异常链经常被 `eventFilter`、`paint`、`drawBranches` 包装，若没有统一定位规则，排查成本会持续偏高。

## 子阶段建议

### 27.1 Theme Chain Inventory And Budget

目标：

- 固定 `MainWindow -> page.update_theme()` 的真实链路和同步预算。

验收要点：

- 每个页面的主题刷新模式明确。
- 至少一份 theme switch 耗时样本可重复执行。

### 27.2 Paint/Delegate Runtime Guardrails

目标：

- 收口项目树换行、自定义 delegate 和共享 widget 绘制路径的运行时安全。

验收要点：

- 至少一条项目树 wrap 路径不再依赖隐式导入。
- 自定义绘制路径具备 smoke test。

### 27.3 Settings Theme Consistency Normalization

目标：

- 统一 settings 页面文本和分组样式的主题刷新约定。

验收要点：

- 已知漏刷的 label 全部被统一纳入刷新或共享 helper。
- 不再新增零散手写样式分支。

## 验收标准

- 主题切换卡顿问题有性能样本和定位证据，而不是只凭主观感受判断。
- 项目树长名称换行、自定义 delegate 和 `eventFilter` 类路径具备运行时 smoke test。
- `SettingsPage` 的主题文本颜色刷新范围被系统化收口。
- 本阶段产物包括检查方法、问题清单、窄测和执行证据，不接受只修单点 bug 就视为完成。

## 提交检查点

- 检查点 1：theme switch 链路与 custom paint inventory 完成。
- 检查点 2：主题性能样本与最小 smoke matrix 固定完成。
- 检查点 3：项目树绘制路径与 settings theme consistency 收口完成。
- 检查点 4：阶段验收提交完成。

## 风险与回退办法

风险：

- 若没有先做 inventory，就直接改 theme/paint 代码，容易再次制造新的隐藏页或委托回归。
- 若性能样本只覆盖空载场景，可能误判真实工作区中的卡顿来源。
- 若 settings 文本样式继续散落在手写 `setStyleSheet()`，后续仍会反复漏刷。

回退办法：

- 若某条主题性能优化无法证明收益，先回退到仅建立样本与测试护栏，不强推实现。
- 若某个 delegate 重写只增加复杂度而没有稳定收益，优先回退到更简单的默认绘制路径。
- 若 settings 文本样式难以一次性统一，先按文本类型建立集中注册表，再分批收口。

## 延后到后续阶段的问题

- 更深层的页面视觉统一和设计语言调整。
- 非主题相关的全仓控件样式重构。
- 更大范围的 UI 性能 profiling 平台化。
