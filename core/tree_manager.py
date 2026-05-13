"""
项目树管理器 — ProjectTree 节点的增删改查、排序、移动、清理

所有方法接受 project: Project 作为第一个参数，
不持有内部状态，便于测试和并行操作。
"""
from __future__ import annotations

from typing import Any, cast, List, Optional, cast

from models.schemas import (
    FolderNode,
    Project,
    ProjectTree,
    TreeNodeUnion,
)

# ── Group type constants ──────────────────────────────

_GROUP_TYPE_ALIASES: dict[str, set[str]] = {
    "datasets": {"datasets", "dataset_set"},
    "source_files": {"source_files"},
    "images": {"images", "image_set"},
    "pictures": {"pictures", "picture_set"},
    "tools": {"tools", "tool_set"},
    "pipeline_group": {"pipeline_group"},
    "template_group": {"template_group", "figure_template_group"},
    "figure_template_group": {"figure_template_group", "template_group"},
    "report_template_group": {"report_template_group"},
    "analysis_result_group": {"analysis_result_group"},
    "ai_group": {"ai_group"},
    "prompt_group": {"prompt_group"},
    "skill_group": {"skill_group"},
    "agent_group": {"agent_group"},
}

_GROUP_DISPLAY_NAMES: dict[str, str] = {
    "datasets": "数据集",
    "source_files": "源文件",
    "images": "数字化",
    "pictures": "图片集",
    "tools": "工具集",
    "pipeline_group": "Pipelines",
    "figure_template_group": "绘图模板组",
    "report_template_group": "报告模板组",
    "analysis_result_group": "分析结果",
    "ai_group": "AI 工具",
    "prompt_group": "Prompts",
    "skill_group": "Skills",
    "agent_group": "Agents",
}

# Root groups in display order
_ROOT_GROUP_ORDER: list[str] = [
    "source_files", "datasets", "pictures", "images", "analysis_result_group",
]

# Group types that should never be cleaned up as empty folders
_NON_REMOVABLE_GROUP_TYPES: set[str] = set(_GROUP_DISPLAY_NAMES.keys())


class TreeManager:
    """树结构管理器，操作 Project.tree 字段。

    所有方法均为静态方法，接受 project: Project 作为第一个参数。
    不持有内部状态，便于测试和并行操作。
    """

    # ── Canonical group type ──────────────────────────

    @staticmethod
    def canonical_group_type(group_type: Optional[str]) -> Optional[str]:
        """标准化 group_type 为规范值。"""
        if group_type is None:
            return None
        canonical_map: dict[str, str] = {
            "dataset_set": "datasets",
            "image_set": "images",
            "picture_set": "pictures",
            "tool_set": "tools",
            "template_group": "figure_template_group",
            "figure_template_group": "figure_template_group",
            "report_template_group": "report_template_group",
            "ai_group": "ai_group",
        }
        if group_type in canonical_map:
            return canonical_map[group_type]
        for canonical, aliases in _GROUP_TYPE_ALIASES.items():
            if group_type == canonical or group_type in aliases:
                return canonical
        return group_type

    # ── Initialization ────────────────────────────────

    @staticmethod
    def ensure_tree(project: Project) -> ProjectTree:
        """确保 project.tree 存在，不存在则创建。"""
        if project.tree is None:
            project.tree = ProjectTree(nodes=[])
        return project.tree

    @staticmethod
    def ensure_root_groups(project: Project) -> None:
        """确保所有根级分组（datasets, images, pictures, source_files 等）存在。

        按固定顺序创建，不重复创建已存在的分组。
        """
        TreeManager.ensure_tree(project)
        tree = project.tree
        assert tree is not None

        for idx, group_type in enumerate(_ROOT_GROUP_ORDER):
            # Check if group already exists
            existing = TreeManager._find_group_folder(project, group_type, parent_id=None)
            if existing is not None:
                # Fix display name / order if drifted
                canonical = TreeManager.canonical_group_type(group_type) or group_type
                display_name = _GROUP_DISPLAY_NAMES.get(canonical, canonical)
                updated = False
                if existing.name != display_name:
                    existing.name = display_name
                    updated = True
                if existing.order != idx:
                    existing.order = idx
                    updated = True
                if updated:
                    project.is_modified = True
                continue

            canonical = TreeManager.canonical_group_type(group_type) or group_type
            display_name = _GROUP_DISPLAY_NAMES.get(canonical, canonical)
            node = FolderNode(
                name=display_name,
                parent_id=None,
                order=idx,
                group_type=cast(Any, canonical),
            )
            tree.nodes.append(node)
            project.is_modified = True

    @staticmethod
    def ensure_group(project: Project, group_type: str, label: str) -> FolderNode:
        """查找或创建指定类型的根分组。

        标签仅在不存在的创建时使用；如果分组已存在则返回已有节点。
        """
        TreeManager.ensure_tree(project)
        existing = TreeManager._find_group_folder(project, group_type, parent_id=None)
        if existing is not None:
            return existing
        canonical = TreeManager.canonical_group_type(group_type) or group_type
        display_name = label or _GROUP_DISPLAY_NAMES.get(canonical, canonical)
        order = len(_ROOT_GROUP_ORDER)  # append after standard groups
        node = FolderNode(
            name=display_name,
            parent_id=None,
            order=order,
            group_type=cast(Any, canonical),
        )
        assert project.tree is not None
        project.tree.nodes.append(node)
        project.is_modified = True
        return node

    # ── CRUD ──────────────────────────────────────────

    @staticmethod
    def add_folder(
        project: Project,
        name: str,
        parent_id: Optional[str] = None,
        group_type: Optional[str] = None,
    ) -> FolderNode:
        """在 parent_id 下添加文件夹。

        parent_id=None 表示挂在项目根。
        """
        tree = TreeManager.ensure_tree(project)
        canonical = TreeManager.canonical_group_type(group_type)
        order = tree.get_siblings_max_order(parent_id) + 1
        node = FolderNode(name=name, parent_id=parent_id, order=order, group_type=cast(Any, canonical))
        tree.nodes.append(node)
        project.is_modified = True
        return node

    @staticmethod
    def add_node(
        project: Project,
        node: TreeNodeUnion,
        parent_id: Optional[str] = None,
    ) -> TreeNodeUnion:
        """将已有节点添加到树中。"""
        tree = TreeManager.ensure_tree(project)
        node.parent_id = parent_id
        node.order = tree.get_siblings_max_order(parent_id) + 1
        tree.nodes.append(node)
        project.is_modified = True
        return node

    @staticmethod
    def delete_node(project: Project, node_id: str) -> bool:
        """删除节点及其所有子节点（递归）。

        仅操作 project.tree，不处理关联的业务数据实体。
        返回是否成功删除（节点不存在返回 False）。
        """
        if project.tree is None:
            return False
        tree = project.tree

        node = tree.get_node(node_id)
        if node is None:
            return False

        # Collect all descendant IDs
        ids_to_delete: set[str] = set()

        def _collect_descendants(parent_id: str) -> None:
            for child in tree.get_children(parent_id):
                ids_to_delete.add(child.id)
                _collect_descendants(child.id)

        ids_to_delete.add(node_id)
        _collect_descendants(node_id)

        tree.nodes = [n for n in tree.nodes if n.id not in ids_to_delete]
        project.is_modified = True
        return True

    @staticmethod
    def rename_node(project: Project, node_id: str, new_name: str) -> bool:
        """重命名树节点。

        仅修改节点名称，不处理关联的业务数据实体重命名。
        返回是否成功（节点不存在或名称为空返回 False）。
        """
        if project.tree is None:
            return False
        node = project.tree.get_node(node_id)
        if node is None:
            return False
        if not (new_name or "").strip():
            return False
        node.name = new_name.strip()
        project.is_modified = True
        return True

    @staticmethod
    def move_node(
        project: Project,
        node_id: str,
        new_parent_id: Optional[str],
    ) -> bool:
        """移动节点到新父节点下（修改 parent_id 和 order）。

        new_parent_id=None 表示移到根。
        不检查目标是否为自己或自己的子节点（调用方保证）。
        返回是否成功（节点不存在返回 False）。
        """
        if project.tree is None:
            return False
        tree = project.tree
        node = tree.get_node(node_id)
        if node is None:
            return False
        node.parent_id = new_parent_id
        node.order = tree.get_siblings_max_order(new_parent_id) + 1
        project.is_modified = True
        return True

    # ── Cleanup ───────────────────────────────────────

    @staticmethod
    def cleanup_empty_folders(project: Project, scope: str = "all") -> int:
        """清理空文件夹。

        scope:
          "all"   — 所有空文件夹（排除不可删除的系统分组）
          "sub"   — 仅非根级空文件夹
          "root"  — 仅根级空文件夹（排除系统分组）
        返回删除数量。
        """
        if project.tree is None:
            return 0
        tree = project.tree
        removed_count = 0

        # Iterate until no more empty folders found (folders may become
        # empty after their children are removed).
        while True:
            empty_ids: list[str] = []
            for node in list(tree.nodes):
                if node.kind != "folder":
                    continue
                is_root = getattr(node, "parent_id", None) is None
                if scope == "sub" and is_root:
                    continue
                if scope == "root" and not is_root:
                    continue

                # Never remove system group folders
                canonical = TreeManager.canonical_group_type(getattr(node, "group_type", None))
                if canonical is not None and canonical in _NON_REMOVABLE_GROUP_TYPES:
                    continue

                # Skip if has children
                if tree.get_children(node.id):
                    continue

                empty_ids.append(node.id)

            if not empty_ids:
                break

            empty_set = set(empty_ids)
            tree.nodes = [n for n in tree.nodes if n.id not in empty_set]
            removed_count += len(empty_ids)

        if removed_count > 0:
            project.is_modified = True
        return removed_count

    # ── Query ─────────────────────────────────────────

    @staticmethod
    def has_children(project: Project, node_id: str) -> bool:
        """检查节点是否有子节点。"""
        if project.tree is None:
            return False
        return len(project.tree.get_children(node_id)) > 0

    @staticmethod
    def find_linked_node(
        project: Project,
        node_kind: str,
        attr_name: str,
        attr_value: str,
    ) -> Optional[TreeNodeUnion]:
        """查找引用了特定数据对象的树节点。

        例如：find_linked_node(project, "data_file", "data_file_id", "abc-123")
        """
        if project.tree is None:
            return None
        return project.tree.find_linked_node(node_kind, attr_name, attr_value)

    @staticmethod
    def get_node(project: Project, node_id: str) -> Optional[TreeNodeUnion]:
        """获取树节点。"""
        if project.tree is None:
            return None
        return project.tree.get_node(node_id)

    @staticmethod
    def get_children(project: Project, parent_id: Optional[str]) -> List[TreeNodeUnion]:
        """获取指定父节点的所有子节点。"""
        if project.tree is None:
            return []
        return project.tree.get_children(parent_id)

    @staticmethod
    def get_siblings_max_order(project: Project, parent_id: Optional[str]) -> int:
        """获取同层节点的最大 order 值。"""
        if project.tree is None:
            return -1
        return project.tree.get_siblings_max_order(parent_id)

    @staticmethod
    def find_folder_by_group_type(
        project: Project,
        group_type: str,
        parent_id: Optional[str] = None,
    ) -> Optional[FolderNode]:
        """按 group_type 查找文件夹节点。"""
        if project.tree is None:
            return None
        canonical = TreeManager.canonical_group_type(group_type) or group_type
        candidates = _GROUP_TYPE_ALIASES.get(canonical, {canonical})
        for node in project.tree.find_nodes(kind="folder", parent_id=parent_id):
            if getattr(node, "group_type", None) in candidates:
                return cast(FolderNode, node)
        return None

    # ── Internal helpers ──────────────────────────────

    @staticmethod
    def _find_group_folder(
        project: Project,
        group_type: str,
        parent_id: Optional[str] = None,
    ) -> Optional[FolderNode]:
        """内部：按 group_type 查找分组文件夹。"""
        return TreeManager.find_folder_by_group_type(project, group_type, parent_id)
