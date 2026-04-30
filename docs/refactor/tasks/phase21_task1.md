# Phase 21 Task 1

## 阶段

- Phase 21 / ui-monolith-completion-and-workspace-surface-hardening

## 对应方案

- `docs/refactor/25-phase-21-ui-monolith-completion-and-workspace-surface-hardening.md`

## 目标

- 先继续拆解 `DataPage` 的高密度页面职责，并收口 `MainWindow` 的页面路由/激活 surface。

## 本任务范围

- `ui/pages/data_page.py`
- `ui/main_window.py`
- 少量直接依赖这些页面的 glue

## 不纳入

- 全新 UI 风格设计
- 全量 UI 回归测试
- 处理算法或扩展协议重写

## 验证

- `./.venv/bin/python -m py_compile ui/pages/data_page.py ui/main_window.py`
- 命中的 data_page / main_window 窄测

## 完成判定

- `DataPage` 的节点路由、右侧内容和页面状态边界开始分离。
- `MainWindow` 不再继续承担页面内部的私有路由细节。
