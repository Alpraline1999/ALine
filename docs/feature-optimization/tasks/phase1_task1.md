# Phase 1 Task 1: 主页暗色/亮色主题背景图切换

## 目标

`_HomeBannerWidget` 当前固定加载 `aline_home_background.png`。
暗色主题时虽然通过 gradient overlay 修正，但未真正切换背景资源。
仓库已存在 `aline_home_background_dark.png`。

## 修改方案

1. 为 `_HomeBannerWidget` 添加 `_current_background_asset_path()`:
   - 亮色 -> `assets/aline_home_background.png`
   - 暗色 -> `assets/aline_home_background_dark.png`
2. 添加 `_reload_background_for_theme()`:
   - 重新加载当前主题对应的背景 pixmap
   - 缓存 pixmap，避免每次 paintEvent 读盘
3. 在 `update_theme()` 中调用 `_reload_background_for_theme()`
4. 简化 `paintEvent()` 中的 gradient overlay（从"补救主视觉"降级为"微调对比度"）
