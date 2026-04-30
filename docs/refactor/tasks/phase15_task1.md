# Phase 15 Task 1

## 阶段

- Phase 15 / monolith-decomposition-and-shared-widget-extraction

## 对应方案

- `docs/refactor/18-phase-15-monolith-decomposition-and-shared-widget-extraction.md`

## 目标

- 对 `DataPage` 做第一轮实质性深拆，先把页面状态与工作区状态边界收口。
- 减少构造期重复初始化，让 `DataPage` 的页面装配状态有明确容器。

## 本任务范围

- `ui/pages/data_page.py`
- `ui/page_view_state.py`
- 与 `DataPage` 紧密耦合的少量桥接代码

## 不纳入

- `project_tree` / `image_viewer` / `extension_options_form` 深拆
- 大规模 UI 视觉改版
- 业务流程重构
- 扩展协议调整

## 验证

- 先做 `py_compile`，再做 `data_page` 相关窄测。
- 不做全量回归测试。

## 完成判定

- `DataPage` 拥有受控页面状态对象，构造期重复初始化收敛。
- 页面边界比前一版更清晰，且不把共享扩展侧栏假设带回去。
