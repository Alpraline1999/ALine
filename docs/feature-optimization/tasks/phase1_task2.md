# Phase 1 Task 2: 曲线列表右键菜单补全可见性动作

## 目标

曲线列表右键菜单缺少显式的批量可见性动作：
- "显示已选中"
- "隐藏已选中"
- "全部显示"

同时确保工具栏按钮和右键菜单调用同一组底层 helper。

## 修改方案

1. 提取统一底层命令：
   - `_set_selected_visibility(visible: bool)` — 设置选中曲线的可见性
   - `_show_all_curves()` — 全部显示
   - `_show_only_selected_curves()` — 仅显示选中（已有）
2. 更新 `_on_chart_list_context_menu()`:
   - 新增 "显示已选中" / "隐藏已选中" / "全部显示" 菜单项
   - 放入独立的 visibility section
3. 确保 `_toggle_selected_visibility()`（工具栏按钮）复用同一底层 helper
