# Phase 33 Task 1: ProjectTreeWidget menu/command/drag-drop support 切分

## 背景

`ProjectTreeWidget` (2159 行) 仍混合了：
- 视图层 (ProjectTreeView)
- 菜单/命令层 (`_on_context_menu`, `_cmd_*`)
- 拖放/目标解析层 (`_perform_drop_*`, `_resolve_drop_target_*`)
- Delegate 绘制 (`_ProjectTreeWrapAnywhereDelegate`)
- 树构建辅助 (`_make_*`, `_build_*`)

已有 extracted modules:
- `project_tree_view.py` — 树视图
- `project_tree_builder.py` — 树构建器
- `project_tree_page_dispatcher.py` — 页面调度
- `project_tree_support.py` — 常量和 helper

## 本次提取目标

1. **Delegate 提取**: 将 `_ProjectTreeWrapAnywhereDelegate` 移入独立的 `project_tree_delegate.py`
2. **Menu/Command 提取**: 将 `_on_context_menu` 及 `_cmd_*` 系列方法移入 `project_tree_menu_commands.py`
   - `_on_context_menu` (~200 行)
   - `_cmd_delete`, `_cmd_add_child_folder`, `_cmd_add_dataset_node`, `_cmd_import_*`, `_cmd_rename_*`, `_cmd_delete_*`, `_cmd_move_*`, `_cmd_prune_empty_folders`
   - `_confirm_tree_delete`, `_prompt_tree_text`, `_prompt_tree_existing_text`, `_notify_tree_*`, `_choose_tree_*`
3. **Drag-drop 提取**: 将拖放相关方法移入 `project_tree_drag_drop.py`
   - `_normalized_source_file_drop_target`, `_perform_source_file_drop_action`, `_open_picture_folder`, `_open_source_file_folder`
   - `_resolve_drop_target_id`, `_resolve_virtual_drop_container_id`, `_perform_drop_move`, `_perform_batch_drop_move`
   - `_finalize_drop_move`, `_finalize_batch_drop_move`
   - `_remember_drag_source_item`, `_remember_drag_source_items`, `_drag_source_item_for_drop`, `_drag_source_items_for_drop`, `_clear_drag_source_item`
4. **ProjectTreeWidget 瘦身**: 提取后 ProjectTreeWidget 只保留 view/signal surface、公开接口、focus/selection 管理

## 验收标准

- ProjectTreeWidget 不再直接包含 delegate 绘制逻辑、context menu 装配、命令执行和拖放规则
- 新增 support 模块可独立测试
- 现有节点选择、双击激活、右键菜单、拖放功能不受影响
