# Phase 13 Final: 项目树拖放与对话框适配层收口

## 目标

修复 `ProjectTreeDragDropHelper` 内部旧私有方法名残留导致的拖放回归，并补一条最小守护测试。

## 实施

1. `ui/widgets/project_tree_drag_drop.py`
   - 将 `perform_drop_move()` 内部调用切换为 `drag_source_item_for_drop()`
   - 保持 helper 自身命名与外层包装命名一致，不再引用已失效的旧私有名
2. `ui/widgets/project_tree.py`
   - 将 `_choose_tree_item()`、`_prompt_tree_text()`、`_prompt_tree_existing_text()` 收口到 `SelectionDialog.get_item()` / `TextInputDialog.get_text()`
   - 清除 `SelectionDialog.get_selected_item()`、`lineEdit` 和错误的构造参数调用
2. `tests/test_ui.py`
   - 增加 helper 直测用例
   - 覆盖 remembered source 的单节点拖放路径，防止同类接口漂移回流
   - 覆盖项目树菜单移动路径和对话框适配层 API

## 验证

- `./.venv/bin/python -m pytest tests/pages/test_home_page.py -q -k 'recent_scroll_expands_to_fill_remaining_height or recent_section_uses_compact_layout_when_empty' tests/test_ui.py -q -k 'drop_move_uses_remembered_drag_source or drag_drop_helper_uses_remembered_drag_source'`
- `./.venv/bin/python -m pytest tests/test_ui.py -q -k 'project_tree_dialog_adapters_use_current_dialog_apis or cmd_move_virtual_uses_selection_dialog'`
- `./.venv/bin/python -m pytest tests/test_project_tree_command_service.py -q -k 'move_virtual_moves_then_refreshes'`

## 后续

- 本阶段仅修复 helper 命名漂移和最小守护，不扩展拖放规则或交互范围。
