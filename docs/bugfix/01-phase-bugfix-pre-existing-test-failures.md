# Bugfix Phase：修复 TestProjectManager 预存测试失败

## 目标与完成定义

修复 `tests/test_backend.py::TestProjectManager` 中 7 个预存失败，
这些失败在 Phase 22-31 旧格式清理之前即已存在，与旧格式无关。

**完成定义：**
- 7 个测试全部通过
- 不引入新失败
- 每个修复点有独立提交

## 问题清单

| # | 测试 | 根因 | 涉及文件 |
|---|------|------|---------|
| 1 | `test_add_data_file_rejects_duplicate_name_in_same_folder` | `ensure_unique_tree_child_name` 重复检测失效，错误信息为空 | `core/project_manager.py` |
| 2 | `test_add_data_file_auto_renames_duplicate_name_when_requested` | `auto_rename_on_conflict` 未生效，名字未自动加后缀 | `core/project_asset_service.py` |
| 3 | `test_move_node_rejects_duplicate_target_sibling_name` | 移动时重复检测失效，错误信息为空 | `core/project_tree_service.py` |
| 4 | `test_delete_node_with_cascade` | 级联删除未从 `project.data_files` 移除实体 | `core/project_tree_service.py` |
| 5 | `test_remove_empty_folders_prunes_nested_user_folders` | `remove_empty_folders` 误删根节点 | `core/project_tree_service.py` |
| 6 | `test_remove_empty_folders_prunes_managed_group_subfolders` | 同上，系统分组根被误删 | `core/project_tree_service.py` |
| 7 | `test_move_source_file_tracks_managed_storage` | 移动后源文件路径未正确更新子目录 | `core/project_manager.py` |

## 实施顺序

1. 先修 `ensure_unique_tree_child_name` 检测逻辑（问题 1/2/3 共享根因）
2. 再修 `delete_node` 级联清理（问题 4）
3. 再修 `remove_empty_folders` 根节点保护（问题 5/6）
4. 最后修源文件路径跟踪（问题 7）
5. 全量验证

## 验收标准

- 全部 7 个测试通过
- backend 回归测试无新增失败
- 每个修复有独立提交，提交信息中文
