# Phase 5 Task 2

## 阶段

- Phase 5 / cleanup-file-splitting-and-dead-path-removal

## 对应方案

- `docs/refactor/06-phase-5-cleanup-file-splitting-and-dead-path-removal.md`

## 目标

- 删除主窗口里残留的旧 AI 桥接与工具上下文适配层。
- 移除设置页里仅用于隐藏助手栏的旧开关/信号。

## 本任务范围

- 清理 `ui/main_window.py` 中所有未再使用的 AI 面板桥接方法与导入。
- 清理 `ui/pages/settings_page.py` 中旧助手栏可见性控制。
- 删除已不再导出的 `ui/widgets/ai_assistant_panel.py`。
- 同步收口相关测试断言。

## 验证

- `python3 -m unittest tests.test_refactor_guardrails`
- `python3 -m py_compile ui/main_window.py ui/pages/settings_page.py ui/widgets/__init__.py tests/test_ui.py`

## 完成判定

- 主窗口不再保留旧 AI 面板桥接或工具上下文适配层。
- 设置页不再暴露仅用于隐藏助手栏的旧控制面。
