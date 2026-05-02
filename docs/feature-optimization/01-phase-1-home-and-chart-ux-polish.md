# Phase 1：主页与可视化页交互抛光

## 目标与完成定义

目标：

- 让首页 banner 真正按主题加载不同背景图。
- 让可视化页曲线列表的批量可见性操作在右键菜单中具备完整入口。

完成定义：

- 暗色/亮色主题切换时，首页 banner 使用对应资源图，而不是只依赖遮罩修正。
- 曲线列表右键菜单至少补齐：
  - 隐藏已选中
  - 显示已选中
  - 仅显示已选中
  - 全部显示
- 工具栏可见性按钮和右键菜单调用同一组 visibility command，不重复维护逻辑。

## 当前代码现状

### 主页

- `_HomeBannerWidget` 当前固定读取 `assets/aline_home_background.png`。
- `paintEvent()` 已区分亮暗主题遮罩，但未切换背景资源。
- 仓库中已存在 `assets/aline_home_background_dark.png`，说明资源准备已完成。

### 可视化页曲线列表

- `ListWidget` 已开启 `ExtendedSelection` 与 `CustomContextMenu`。
- `_toggle_selected_visibility()` 已实现批量切换可见性。
- `_on_chart_list_context_menu()` 当前只有：
  - 重命名显示名称
  - 恢复原始名称
  - 仅显示选中

## 优化方案

### 1. 首页主题背景图方案

推荐方案：

- 为 `_HomeBannerWidget` 引入 theme-aware background resolver：
  - 亮色 -> `aline_home_background.png`
  - 暗色 -> `aline_home_background_dark.png`
- 保留现有 gradient overlay，但降低它从“补救主视觉”变成“精调对比度”的角色。
- 主题切换时只刷新 banner 的缓存 pixmap，不重复做不必要的磁盘读取。

实现边界建议：

- 不要把主题背景逻辑分散到 `paintEvent()` 和 `update_theme()` 两边各写一半。
- 应抽成单一 helper，例如：
  - `_current_background_asset_path()`
  - `_reload_background_for_theme()`

验收要点：

- 切换主题后首页背景图资源发生真实变化。
- 亮暗主题下标题、说明、链接卡片的对比度都不下降。
- 若暗色资源缺失，仍回退到当前遮罩 + fallback color 路径。

### 2. 曲线列表右键菜单可见性动作方案

推荐方案：

- 在 `_on_chart_list_context_menu()` 中引入显式 visibility section。
- 以“当前多选集合”为作用范围，而不是仅当前 item。

建议动作集：

- `隐藏已选中`
- `显示已选中`
- `仅显示已选中`
- `全部显示`

实现边界建议：

- 不在每个 QAction 内直接改 `curve["visible"]`。
- 提取统一命令层，例如：
  - `_set_selected_visibility(visible: bool)`
  - `_show_only_selected_curves()`
  - `_show_all_curves()`
- 工具栏按钮 `_toggle_selected_visibility()` 也应复用同一底层 helper。

验收要点：

- 单选和多选时，右键菜单动作行为一致。
- 执行动作后：
  - 列表前缀 `[隐藏]`
  - 灰色文本
  - 图表 redraw
  - 当前选中项
  都保持一致。

## 本阶段不纳入的范围

- 扩展样式优先级重构
- 曲线列表恢复历史快照
- 首页链接卡片内容替换

## 风险与回退

风险：

- 主题资源切换若做成每次 paint 读文件，会引入不必要的渲染开销。
- 多选上下文菜单若仍依赖 `currentItem` 而不是 `selectedItems()`，容易出现误操作。

回退方式：

- 若首页暗色资源效果不理想，先接入双资源机制并保留现有渐变参数，再单独调视觉。
- 若右键多选行为与现有 toolbar 冲突，先统一底层 helper，再回接 UI 动作。
