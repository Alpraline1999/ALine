# Phase 14 Final: 项目树分组语义与导出目标归属规范化

## 目标

统一项目树根分组、普通子文件夹、导出目标创建与图标展示的语义，避免用户在树上看到的内容与实际归属继续分叉。

## 实施

1. `ui/pages/save_export_coordinator.py`
   - 支持显式传入 `folder_group_type`
   - 让自动创建目录时的 `group_type` 与目标集合一致
2. `ui/pages/analysis_page.py`、`ui/pages/digitize_page.py`
   - 将自动创建导出目录的目标分组固定为 `datasets`
   - 保持分析结果导出和数字化结果导出的目录归属一致
3. `ui/widgets/project_tree.py`
   - 限制系统分组图标只出现在根分组文件夹
   - 普通子文件夹统一显示为普通 folder 图标
4. `tests/test_ui.py`
   - 增加分析结果导出自动创建数据集子文件夹的窄测
   - 增加普通子文件夹 icon 统一规则的窄测
5. `docs/feature-optimization/14-phase-14-project-tree-group-semantics-and-export-target-normalization.md`
   - 记录 phase14 的问题背景、边界和验收标准

## 验证

- `./.venv/bin/python -m pytest tests/test_ui.py -q -k 'project_tree_icons_follow_updated_asset_mapping or project_tree_child_folders_use_plain_folder_icon or analysis_result_export_auto_creates_dataset_folder'`
- `./.venv/bin/python -m pytest tests/test_project_tree_command_service.py -q -k 'move_virtual_moves_then_refreshes'`

## 后续

- phase14 仅收口项目树分组语义和导出目标归属，不继续扩展新的批量导出或树视觉重设计。

