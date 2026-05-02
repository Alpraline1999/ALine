# Phase 2：可视化页样式优先级与扩展契约

## 目标与完成定义

目标：

- 消除“绘图扩展覆盖曲线样式/绘图样式设置”的不确定感。
- 把当前实现层的 patch/sequence 机制，提升为用户可理解的样式优先级契约。

完成定义：

- 明确规定曲线样式、绘图样式、模板、扩展 patch 的生效顺序。
- 用户能知道当前生效值来自哪里。
- 扩展是否允许覆盖手动样式，成为显式策略，而不是隐含行为。

## 当前代码现状

### 已有机制

- 基础曲线样式与基础绘图样式已作为 hidden base extensions 存在。
- `PlotExtensionContext` 支持：
  - `patch_figure_state()`
  - `patch_plot_style()`
  - `patch_selected_curve_style()`
- `ChartPage._redraw_now()` 会收集 `before_plot` 扩展 patch，然后通过：
  - `_effective_plot_figure_state_payload()`
  - `_effective_plot_style_extras()`
  - `_effective_curve_style_payloads()`
  按 sequence 与手动变更版本号做合并。

### 当前问题

- 规则是“实现存在、产品语义缺失”。
- 用户不清楚当前优先级究竟是：
  - 模板优先
  - 手动优先
  - 扩展优先
  - 最后应用者优先
- `after_plot` 扩展还能直接改 artist，进一步放大了“为什么我的样式又变了”的困惑。

## 推荐契约

### 默认优先级

推荐把样式栈定义为：

1. 源数据默认值
2. 全局模板/加载模板
3. 扩展建议 patch
4. 用户手动曲线样式/绘图样式修改
5. 明确声明为“强制覆盖”的扩展 patch

解释：

- 普通扩展默认应是“增强和建议”，不是抢走最终控制权。
- 用户在 UI 面板里手动改的值，默认应该是最终值。
- 只有当扩展明确声明“我需要接管某些字段”时，才允许覆盖手动值。

### 扩展 patch 分类

推荐新增两类语义：

- `advisory patch`
  - 默认类型
  - 不能覆盖同字段的手动修改
- `authoritative patch`
  - 需要显式声明
  - 可覆盖指定字段
  - UI 中应提示“该扩展接管了哪些字段”

### 字段级控制

推荐按字段而不是整条曲线/整套 plot style 做控制：

- 曲线级字段：
  - `color`
  - `linestyle`
  - `marker`
  - `linewidth`
  - `marker_size`
  - `alpha`
  - `markevery`
  - `dash_scale`
  - `visible`
- 绘图级字段：
  - `figure_state` 中的轴标题、图例、网格等
  - `plot_style_extras` 中的 `tick_params`、`legend_kwargs`、`grid_kwargs` 等

### after_plot 规则

推荐额外加一条产品约束：

- `after_plot` 扩展默认不参与“样式值所有权”承诺。
- 它属于 post-render mutation。
- 若某个扩展必须在 `after_plot` 改 artist 样式，应在 UI 中声明“此扩展会直接改最终图元，可能覆盖面板设置”。

## 实现建议

### 方案 A：基于现有 sequence 机制增量改造

推荐优先采用。

做法：

- 保留现有 `*_change_versions` 与 sequence 机制。
- 为扩展 patch 增加 `authority` 元数据：
  - `advisory`
  - `authoritative`
- 在 `_effective_*` 合并函数中加入 authority 判断。

优点：

- 改动集中在样式合并层，不需要推翻整个绘图页结构。
- 能保持当前 snapshot / restore / applied extension 数据模型的大致稳定。

### 方案 B：把样式来源完整建模

更彻底，但不建议作为第一步。

做法：

- 为每个字段记录 source，例如：
  - `manual`
  - `template`
  - `extension:<type>:<instance>`
- UI 能直接展示来源标签。

优点：

- 可解释性最强。

缺点：

- 侵入面更大。
- 会影响 snapshot、restore、extension panel、style tab 的数据结构。

## 验收标准

- 手动修改曲线样式/绘图样式后，普通扩展不会无提示地把它改回去。
- 若扩展确实覆盖了字段，用户能知道：
  - 是哪个扩展
  - 覆盖了哪些字段
  - 是否允许解除接管
- 同一扩展在 `before_plot` 和 `after_plot` 阶段的影响范围被清晰区分。

## 本阶段不纳入的范围

- 重写整个扩展 API
- 删除现有 sequence/version 机制
- 重做曲线样式与绘图样式 UI 布局

## 风险与回退

风险：

- 如果直接把所有扩展都改成“手动样式永远优先”，可能破坏一部分依赖强制输出风格的扩展。
- 如果 authority 语义定义过粗，会让“部分字段可覆盖、部分字段不可覆盖”的场景仍然混乱。

回退方式：

- 先引入 advisory/authoritative 二分，不立即要求所有扩展声明细粒度字段策略。
- 先针对可视化页内建/常用扩展落约束，再逐步扩展到外部扩展。
