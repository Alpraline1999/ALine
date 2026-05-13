# Phase 27 Task 3: 项目树虚拟滚动

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`，阶段 `Phase 27`

## 目标

将 `ProjectTreeWidget` 从 `QTreeWidget`（一次性加载全部节点）迁移为 `QTreeView` + 自定义 `QAbstractItemModel`，实现大数据集（500+ 节点）的按需加载和虚拟滚动。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `ui/widgets/project_tree.py` | 重构数据模型层 |

## 方案

### 现有问题

`QTreeWidget` 在节点展开时创建全部子节点的 `QTreeWidgetItem` 对象，500+ 节点时展开/折叠卡顿。

### 设计方案

保留 `QTreeWidget` 的 UI 层（样式、拖放、右键菜单、选中状态等），仅在数据模型层优化：

1. **分层模型**：节点数据不直接创建 `QTreeWidgetItem`，而是从 `ProjectTree` 模型直接创建 widget item
2. **展开时按需构建**：初始只构建根级节点，子节点展开时才创建 item
3. **缓存 item**：已加载的 item 缓存起来，折叠后不销毁

```python
class ProjectTreeModel:
    """项目树数据模型，从 ProjectTree.nodes 读取。
    
    职责：
    - 将 ProjectTree 扁平节点列表映射为树形 Widget Item
    - 按需加载子节点（仅在展开时）
    - item 缓存（展开后不销毁，折叠后保留）
    """
    
    def __init__(self, tree_widget):
        self._widget = tree_widget
        self._item_cache: Dict[str, QTreeWidgetItem] = {}
    
    def build_initial(self, project_tree: ProjectTree):
        """构建根级节点（展开根组）。"""
        self._widget.clear()
        self._item_cache.clear()
        
        root_nodes = project_tree.get_children(parent_id=None)
        for node in sorted(root_nodes, key=lambda n: n.order):
            item = self._create_item(node)
            self._widget.addTopLevelItem(item)
            
            # 如果节点有子节点，添加一个占位 item（使展开箭头可见）
            children = project_tree.get_children(node.id)
            if children:
                placeholder = QTreeWidgetItem()
                item.addChild(placeholder)
    
    def on_before_expand(self, item: QTreeWidgetItem):
        """节点展开前：移除占位 item，加载真实子节点。"""
        node_id = item.data(0, Qt.UserRole)
        project = project_manager.current_project
        if project and project.tree:
            children = project.tree.get_children(node_id)
            
            # 移除占位
            if item.childCount() == 1:
                placeholder = item.child(0)
                if placeholder and not placeholder.data(0, Qt.UserRole):
                    item.removeChild(placeholder)
            
            # 加载真实子节点
            for node in children:
                child_item = self._get_or_create_item(node)
                item.addChild(child_item)
    
    def _get_or_create_item(self, node) -> QTreeWidgetItem:
        if node.id in self._item_cache:
            return self._item_cache[node.id]
        return self._create_item(node)
    
    def _create_item(self, node) -> QTreeWidgetItem:
        item = QTreeWidgetItem()
        item.setText(0, node.name)
        item.setData(0, Qt.UserRole, node.id)
        item.setData(0, Qt.UserRole + 1, node.kind)
        self._item_cache[node.id] = item
        
        # 如果是文件夹，添加占位
        if node.kind == "folder" or node.kind in ("dataset_set", "image_set", ...):
            placeholder = QTreeWidgetItem()
            item.addChild(placeholder)
        
        return item
```

## 与现有功能的兼容

- **拖放**：仍然基于 `QTreeWidgetItem`，不受影响
- **右键菜单**：通过 `item.data()` 获取 node_id 和 kind，不受影响
- **搜索/过滤**：在 model 层过滤可见性即可
- **展开状态恢复**：`expanded_node_ids` 列表用于恢复已展开的节点

## 验证清单

- [ ] 500 节点项目树展开全部根组无卡顿
- [ ] 节点过滤功能正常
- [ ] 拖放移动节点正常
- [ ] 右键菜单功能正常
- [ ] 展开状态在页面切换后保持

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`
