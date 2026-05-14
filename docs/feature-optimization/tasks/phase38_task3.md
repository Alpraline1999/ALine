# Phase 38 Task 3: 样式与交互等价迁移

## 目标

把现有项目树的样式、delegate、拖放、右键菜单、多选和 tooltip 行为迁移到 `QTreeView` 架构下。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `ui/widgets/project_tree_view.py` | 新 view 行为接线 |
| `ui/widgets/project_tree_delegate.py` | wrap/size hint 等样式等价迁移 |
| `ui/widgets/project_tree_drag_drop.py` | 基于 model index 的拖放适配 |
| `ui/widgets/project_tree_menu_commands.py` | 基于 model index 的右键菜单适配 |

## 验收清单

- [ ] 长名称换行、tooltip、图标样式不明显退化
- [ ] 拖放、右键、多选、F2 重命名仍可用
