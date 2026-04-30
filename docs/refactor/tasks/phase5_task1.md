# Phase 5 Task 1

## 阶段

- Phase 5 / cleanup-file-splitting-and-dead-path-removal

## 对应方案

- `docs/refactor/06-phase-5-cleanup-file-splitting-and-dead-path-removal.md`

## 目标

- 清理主 UI 链路中的隐藏 AI 面板和隐藏设置入口。
- 让用户路径不再保留暂停或隐藏的 AI 入口。

## 本任务范围

- 移除主窗口里的隐藏 AI 面板按钮和路由。
- 移除设置页里的隐藏 AI tab 入口。
- 保留其余 AI 数据结构与历史兼容代码，后续再继续清理。

## 验证

- `python3 -m unittest tests.test_refactor_guardrails`
- `python3 -m py_compile ui/main_window.py ui/pages/settings_page.py tests/test_refactor_guardrails.py`

## 完成判定

- 主 UI 链路里不再存在隐藏 AI 面板和隐藏设置入口。
