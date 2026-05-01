# Phase 34 Task 1: 扫描 project_manager._* 调用点并创建 public facade

## 发现的调用点

1. `project_manager._find_folder_by_group_type("datasets")`
   - ui/pages/digitize_page.py:1940, 1956
   - ui/pages/analysis_page.py:2153, 2229
2. `project_manager._normalize_name_key(name)`
   - ui/pages/process_page.py:1499, 1522, 1523
3. `project_manager._canonical_group_type(...)`
   - ui/dialogs/export_flow.py:946
4. `project_manager._current_project_id = None`
   - ui/pages/digitize_page.py:2377

## 修复方案

1. 添加 `find_folder_by_group_type(group_type, parent_id=None)` public 方法
2. 添加 `normalize_name_key(name)` public 方法（已存在 `_normalize_name_key` 静态方法，改为 public）
3. 添加 `canonical_group_type(group_type)` public 方法（已有对应 `_canonical_group_type`）
4. 添加 `clear_current_project()` 方法清除 session
