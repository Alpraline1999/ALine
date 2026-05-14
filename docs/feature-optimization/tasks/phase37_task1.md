# Phase 37 Task 1: 语言配置与运行时加载

## 目标

让 `core/i18n.py` 从用户配置加载语言，而不是固定 `zh_CN`。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `core/i18n.py` | locale 选择与 fallback 调整 |
| `core/ui_preferences.py` 或等效配置模块 | 语言偏好持久化 |

## 验收清单

- [ ] 语言配置可读写
- [ ] 应用启动时按配置加载 locale
