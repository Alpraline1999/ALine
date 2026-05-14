# Phase 38 Task 2: QAbstractItemModel 实现

## 目标

实现项目树专用 `QAbstractItemModel`，承载节点文本、图标、tooltip、父子索引和懒加载能力。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `ui/widgets/project_tree_model.py` | **新建**：项目树 model |
| `ui/widgets/project_tree.py` | 接入 model |

## 验收清单

- [ ] 基本展示正常
- [ ] 懒加载与展开状态恢复正常
- [ ] 500+ 节点场景性能优于旧实现
