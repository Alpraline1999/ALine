# Phase 28 Task 1：Settings/UI 样式契约与生命周期硬化

## 目标

- 把 `SettingsPage` 里设置卡片标题、描述、次级状态和少量局部说明的主题样式收口到统一注册机制。
- 清理延后刷新路径上的已删除对象噪声，确保窄测和关闭路径不会反复产出误导性 RuntimeError。
- 用窄范围测试固定标题/描述样式一致性和生命周期安全。

## 任务拆分

1. 审核 `ui/pages/settings_page.py` 中仍然存在的直接 `setStyleSheet()` 入口，补齐所有应受控的主题文本。
2. 为 `SettingsPage` 的延后刷新路径补充更稳健的销毁期 guard，尤其是扩展分类 tab 高度刷新。
3. 增补 settings 主题一致性与生命周期安全的窄测。
4. 按 `important-change-commit` 形成本阶段检查点提交。

## 验收方式

- `py_compile` 通过。
- 仅运行本阶段相关的 settings/main-window 窄测。
- 提交信息使用中文，说明背景、修改和验证。
