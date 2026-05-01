# Phase 29 Task 1：共享项目树与设置面深拆

## 目标

- 把 `SettingsPage` 中最重的扩展页构建逻辑抽到明确的 support 模块，减少壳层职责。
- 顺手清理 `ProjectTreeWidget` 里还能独立出来的轻量 support 边界，避免壳层继续吸纳新逻辑。
- 为后续 Phase 30 的包面合并留出更干净的 UI 入口边界。

## 任务拆分

1. 将 `SettingsPage` 的扩展页/扩展分类 tab 构建逻辑提取到 `ui/pages/settings_page_support.py`。
2. 将 `SettingsPage` 中与扩展目录列表相关的可复用控件迁移到 support 模块。
3. 检查 `ProjectTreeWidget` 当前 support 分层，补一个小范围提取或整理，确保壳层不再持有不必要的支持逻辑。
4. 补充围绕新 support 模块和现有壳层入口的窄测。
5. 使用 `important-change-commit` 形成 Phase 29 检查点提交。

## 验收方式

- `py_compile` 通过。
- 设置页扩展相关窄测和项目树对应窄测通过。
- 提交说明清楚描述“为什么拆、拆了什么、验证了什么”。
