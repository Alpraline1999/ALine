# Phase 22 Task 2: 抽取 TreeManager

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `start`/`checkpoint`，阶段 `Phase 22`

## 目标

从 `core/project_manager.py` 中提取所有项目树管理方法（约 30-50 个方法）为独立的 `core/tree_manager.py` 模块。`ProjectManager` 中保留委托调用，页面调用方逐步迁移。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `core/project_manager.py` | 移除树管理方法，改为委托 `TreeManager` |
| `core/tree_manager.py` | **新建** |
| `ui/widgets/project_tree.py` | 逐步将引用从 `project_manager` 迁移到 `tree_manager` |
| `ui/pages/data_page.py` | 同上 |
| `ui/main_window.py` | 同上 |
| `tests/test_backend.py` | 补充 `TestTreeManager` 单元测试 |

## 详细实施步骤

### Step 1: 从 ProjectManager 中识别树方法

搜索 `core/project_manager.py` 中的以下模式：

```python
# 树结构初始化
_ensure_tree()
_ensure_root_groups()
_ensure_group_*()  # 多种 group_type 的 ensure

# 节点 CRUD
add_folder()          # 公开
add_node()            # 公开
_delete_node()        # 內部
_add_folder_node()    # 内部辅助

# 节点管理
rename_node()         # 公开
reorder_node()        # 公开
move_node()           # 公开

# 清理
cleanup_empty_folders()     # 公开
cleanup_empty_subfolders()  # 公开

# 节点存在性
_has_children()
_find_tree_linked_node()
_node_exists_in_tree()

# 排序
_get_node_order()
_set_node_order()

# 其他树查询
get_tree()  # 如果存在
```

### Step 2: 实现 TreeManager

```python
# core/tree_manager.py
"""项目树管理器 — ProjectTree 节点的增删改查、排序、移动、清理"""

from __future__ import annotations
from typing import Optional, List, Dict

from models.schemas import (
    Project, ProjectTree, FolderNode, GroupType,
    TreeNodeUnion, DataFileNode, SourceFileNode,
    ...
)


class TreeManager:
    """树结构管理器，操作 Project.tree 字段。
    
    所有方法接受 project: Project 作为第一个参数，
    不持有内部状态，便于测试和并行操作。
    """
    
    # ── 初始化 ──
    
    @staticmethod
    def ensure_tree(project: Project) -> ProjectTree:
        """确保 project.tree 存在，不存在则创建。"""
        if project.tree is None:
            project.tree = ProjectTree(nodes=[])
        return project.tree
    
    @staticmethod
    def ensure_root_groups(project: Project) -> None:
        """确保所有根级分组（datasets, images, pictures, tools 等）存在。"""
        ...
    
    @staticmethod
    def ensure_group(project: Project, group_type: str, label: str) -> FolderNode:
        """查找或创建指定类型的根分组。标签不存在时才创建。"""
        ...
    
    # ── CRUD ──
    
    @staticmethod
    def add_folder(project: Project, name: str, parent_id: Optional[str] = None) -> FolderNode:
        """在 parent_id 下添加文件夹。
        
        parent_id=None 表示挂在项目根。
        """
        tree = TreeManager.ensure_tree(project)
        node = FolderNode(name=name, parent_id=parent_id, order=tree.get_siblings_max_order(parent_id) + 1)
        tree.nodes.append(node)
        return node
    
    @staticmethod
    def add_node(project: Project, node: TreeNodeUnion, parent_id: Optional[str] = None) -> TreeNodeUnion:
        """将已有节点添加到树中。"""
        node.parent_id = parent_id
        node.order = project.tree.get_siblings_max_order(parent_id) + 1
        project.tree.nodes.append(node)
        return node
    
    @staticmethod
    def delete_node(project: Project, node_id: str) -> bool:
        """删除节点及其所有子节点。children 优先于 parent 删除。"""
        node = project.tree.get_node(node_id)
        if node is None:
            return False
        # 递归删除子节点
        children = project.tree.get_children(node_id)
        for child in children:
            TreeManager.delete_node(project, child.id)
        project.tree.nodes = [n for n in project.tree.nodes if n.id != node_id]
        return True
    
    @staticmethod
    def move_node(project: Project, node_id: str, new_parent_id: Optional[str]) -> bool:
        """移动节点到新父节点下。
        
        new_parent_id=None 表示移到根。
        不检查目标是否为自己或自己的子节点（调用方保证）。
        """
        node = project.tree.get_node(node_id)
        if node is None:
            return False
        node.parent_id = new_parent_id
        node.order = project.tree.get_siblings_max_order(new_parent_id) + 1
        return True
    
    @staticmethod
    def rename_node(project: Project, node_id: str, new_name: str) -> bool:
        """重命名节点。"""
        node = project.tree.get_node(node_id)
        if node is None:
            return False
        node.name = new_name
        return True
    
    # ── 清理 ──
    
    @staticmethod
    def cleanup_empty_folders(project: Project, scope: str = "all") -> int:
        """清理空文件夹。
        
        scope:
          "all"     — 所有空文件夹
          "sub"     — 仅非根级空文件夹
          "root"    — 仅根级空文件夹
        返回删除数量。
        """
        ...
    
    # ── 查询 ──
    
    @staticmethod
    def has_children(project: Project, node_id: str) -> bool:
        return len(project.tree.get_children(node_id)) > 0
    
    @staticmethod
    def find_linked_node(project: Project, node_kind: str, attr_name: str, attr_value: str):
        """查找引用了特定数据对象的节点。"""
        if project.tree is None:
            return None
        return project.tree.find_linked_node(node_kind, attr_name, attr_value)
```

### Step 3: 在 ProjectManager 中替换

```python
# core/project_manager.py
from core.tree_manager import TreeManager

class ProjectManager:
    def __init__(self):
        self._tree_manager = TreeManager()
    
    # 原有方法改为委托:
    def add_folder(self, *args, **kwargs):
        return self._tree_manager.add_folder(self.current_project, *args, **kwargs)
    
    def add_node(self, *args, **kwargs):
        return self._tree_manager.add_node(self.current_project, *args, **kwargs)
    
    def delete_node(self, node_id):
        return self._tree_manager.delete_node(self.current_project, node_id)
    
    # 以此类推 ...
    
    # 方法名变更的注意：
    # _delete_node → delete_node（公开化）
    # _has_children → has_children（公开化）
    # 调用方需要同步更新
```

### Step 4: 更新调用方引用

搜索 `project_manager._delete_node(`、`project_manager.add_folder(` 等模式，迁移到直接使用 `tree_manager`：

```python
# ui/widgets/project_tree.py
from core.tree_manager import TreeManager

# 调用处
TreeManager.delete_node(project_manager.current_project, node_id)
```

**迁移策略**：先全部走委托路径（不修改调用方），全部测试通过后再逐步迁移调用方。

### Step 5: 单元测试

```python
# tests/test_backend.py — 追加
class TestTreeManager(unittest.TestCase):
    def setUp(self):
        self.mgr = TreeManager()
        self.project = Project.create_new("test")
    
    def test_ensure_tree_creates_when_none(self):
        self.assertIsNone(self.project.tree)
        self.mgr.ensure_tree(self.project)
        self.assertIsNotNone(self.project.tree)
    
    def test_add_folder_increases_node_count(self):
        self.mgr.ensure_tree(self.project)
        n_before = len(self.project.tree.nodes)
        self.mgr.add_folder(self.project, "test")
        self.assertEqual(len(self.project.tree.nodes), n_before + 1)
    
    def test_add_folder_with_parent(self):
        self.mgr.ensure_root_groups(self.project)
        parent = self.mgr.ensure_group(self.project, "datasets", "数据集")
        child = self.mgr.add_folder(self.project, "sub", parent.id)
        self.assertEqual(child.parent_id, parent.id)
    
    def test_delete_node_removes_node(self):
        self.mgr.ensure_root_groups(self.project)
        n_before = len(self.project.tree.nodes)
        # 删除一个已知根节点
        ds_group = self.mgr.ensure_group(self.project, "datasets", "数据集")
        self.mgr.delete_node(self.project, ds_group.id)
        self.assertLess(len(self.project.tree.nodes), n_before)
    
    def test_delete_node_with_children(self):
        """删除父节点时子节点也被删除"""
        parent = self.mgr.add_folder(self.project, "parent")
        child = self.mgr.add_folder(self.project, "child", parent.id)
        self.mgr.delete_node(self.project, parent.id)
        self.assertIsNone(self.project.tree.get_node(child.id))
    
    def test_move_node_changes_parent(self):
        folder1 = self.mgr.add_folder(self.project, "f1")
        folder2 = self.mgr.add_folder(self.project, "f2")
        child = self.mgr.add_folder(self.project, "child", folder1.id)
        self.mgr.move_node(self.project, child.id, folder2.id)
        self.assertEqual(child.parent_id, folder2.id)
    
    def test_rename_node(self):
        node = self.mgr.add_folder(self.project, "old")
        self.mgr.rename_node(self.project, node.id, "new")
        self.assertEqual(node.name, "new")
    
    def test_cleanup_empty_folders_removes_empty(self):
        empty = self.mgr.add_folder(self.project, "empty")
        full = self.mgr.add_folder(self.project, "full")
        self.mgr.add_folder(self.project, "child", full.id)
        count = self.mgr.cleanup_empty_folders(self.project, "sub")
        self.assertEqual(count, 1)
        self.assertIsNone(self.project.tree.get_node(empty.id))
```

## 边界情况与错误处理

| 场景 | 预期行为 |
|---|---|
| 删除不存在的节点 | 返回 False |
| 移动节点到自己之下 | 调用方保证不传（或方法内检测并返回 False） |
| 重命名空字符串 | 返回 False，不修改 |
| project.tree 为 None | 所有 CRUD 方法先调用 ensure_tree |
| 清理空文件夹时根级 vs 子级 | scope 参数区分，默认只清理子级 |

## 验证清单

- [ ] `python -m pytest tests/test_backend.py -k TestTreeManager -q` 全部通过
- [ ] 在 UI 中：项目树可展开根组，添加文件夹，拖放移动，删除，重命名
- [ ] "清理空文件夹"在根级和子级都工作正常
- [ ] 所有原有 `project_manager.delete_node/add_folder` 等调用仍然有效（委托路径）

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`
