from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional


def normalize_name_key(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip()).casefold()


def ensure_non_empty_name(name: str, *, label: str = "名称") -> tuple[bool, Optional[str]]:
    if normalize_name_key(name):
        return True, None
    return False, f"{label}不能为空"


def has_tree_child_name_conflict(
    project: Any,
    parent_id: Optional[str],
    name: str,
    *,
    node_kind: Optional[str] = None,
    exclude_node_id: Optional[str] = None,
) -> bool:
    if project is None or getattr(project, "tree", None) is None:
        return False
    normalized = normalize_name_key(name)
    for sibling in project.tree.get_children(parent_id):
        if exclude_node_id is not None and sibling.id == exclude_node_id:
            continue
        if node_kind is not None and getattr(sibling, "kind", None) != node_kind:
            continue
        if normalize_name_key(getattr(sibling, "name", "")) == normalized:
            return True
    return False


def split_name_suffix(name: str) -> tuple[str, str]:
    clean_name = (name or "").strip()
    if not clean_name:
        return "", ""
    suffixes = Path(clean_name).suffixes
    suffix = "".join(suffixes)
    if suffix and clean_name.endswith(suffix):
        stem = clean_name[: -len(suffix)]
        if stem:
            return stem, suffix
    return clean_name, ""


def ensure_unique_tree_child_name(
    project: Any,
    parent_id: Optional[str],
    name: str,
    *,
    node_kind: Optional[str] = None,
    exclude_node_id: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    if project is None or getattr(project, "tree", None) is None:
        return ensure_non_empty_name(name)
    ok, error = ensure_non_empty_name(name)
    if not ok:
        return ok, error
    if has_tree_child_name_conflict(
        project,
        parent_id,
        name,
        node_kind=node_kind,
        exclude_node_id=exclude_node_id,
    ):
        parent = project.tree.get_node(parent_id) if parent_id else None
        scope_label = "当前层级"
        if parent is not None and getattr(parent, "kind", None) == "folder":
            scope_label = f"文件夹“{parent.name or '未命名文件夹'}”"
        return False, f"{scope_label}下已存在名为“{name.strip()}”的节点，请先重命名后再试。"
    return True, None


def next_unique_tree_child_name(
    project: Any,
    parent_id: Optional[str],
    name: str,
    *,
    node_kind: Optional[str] = None,
    exclude_node_id: Optional[str] = None,
) -> str:
    candidate = (name or "").strip()
    if not candidate:
        return candidate
    if project is None or getattr(project, "tree", None) is None:
        return candidate
    if not has_tree_child_name_conflict(
        project,
        parent_id,
        candidate,
        node_kind=node_kind,
        exclude_node_id=exclude_node_id,
    ):
        return candidate
    stem, suffix = split_name_suffix(candidate)
    index = 1
    while True:
        renamed = f"{stem}_{index}{suffix}"
        if not has_tree_child_name_conflict(
            project,
            parent_id,
            renamed,
            node_kind=node_kind,
            exclude_node_id=exclude_node_id,
        ):
            return renamed
        index += 1
