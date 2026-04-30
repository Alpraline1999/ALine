# Phase 12 Task 1

## 阶段

- Phase 12 / ui-page-decomposition-and-shell-normalization

## 对应方案

- `docs/refactor/14-phase-12-ui-page-decomposition-and-shell-normalization.md`

## 目标

- 从大页面里先剥离一组可复用的 UI 壳层/布局辅助逻辑。
- 为后续页面拆分建立共享骨架，减少重复的 splitter / panel / visibility 代码。
- 同步修复设置页在旧调用路径下的模板刷新容错问题，避免主窗口关闭项目时触发运行时异常。

## 本任务范围

- 盘点 `chart_page`、`analysis_page`、`process_page`、`digitize_page` 的公共布局逻辑。
- 提取一组不依赖具体业务的页面壳层辅助函数，优先覆盖 splitter 复位与扩展面板显隐。
- 用最小范围接入一个或多个页面，验证边界不被破坏。
- 让 `SettingsPage.refresh_templates()` 对缺失的模板列表属性保持兼容。

## 不纳入

- 扩展协议重构
- 曲线热路径优化
- UI 风格和冗余收尾

## 验证

- 以相关页面窄测和 UI smoke 的小范围验证为准。
- 不做全量回归测试。
- 至少补一组针对壳层 helper 和设置页模板刷新路径的窄测。

## 完成判定

- 至少一组跨页面的布局/壳层辅助逻辑被抽出。
- 接入页面的行为未退化。
- 后续页面拆分路径已经明确。
