from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from core.project_manager import project_manager
from ui.dialogs.fluent_dialogs import SelectionDialog, TextInputDialog


@dataclass(frozen=True)
class DataExportPlan:
    export_name: str
    target_data_file_id: Optional[str] = None
    new_parent_id: Optional[str] = None
    new_data_file_name: Optional[str] = None


@dataclass(frozen=True)
class PictureExportPlan:
    export_name: str
    target_folder_id: Optional[str]


def choose_data_export_plan(
    parent,
    *,
    title: str,
    default_export_name: str,
    default_file_name: str,
    preferred_target_node_id: Optional[str] = None,
    file_suffix: str = ".data",
) -> Optional[DataExportPlan]:
    project = project_manager.current_project
    if project is None or project.tree is None:
        return None

    export_name, ok = TextInputDialog.get_text(
        parent,
        title,
        "名称:",
        text=(default_export_name or "").strip(),
        placeholder="输入导出名称",
    )
    export_name = export_name.strip()
    if not ok or not export_name:
        return None

    entries = _build_data_target_entries()
    if not entries:
        return None
    current_text = _preferred_target_label(entries, preferred_target_node_id)
    selected_label, ok = SelectionDialog.get_item(
        parent,
        title,
        "目标:",
        [entry["label"] for entry in entries],
        current_text=current_text,
    )
    if not ok or not selected_label:
        return None
    selected_entry = next((entry for entry in entries if entry["label"] == selected_label), None)
    if selected_entry is None:
        return None
    if selected_entry["mode"] == "append":
        return DataExportPlan(export_name=export_name, target_data_file_id=selected_entry["data_file_id"])

    file_name, ok = TextInputDialog.get_text(
        parent,
        "新建数据文件",
        "数据文件名称:",
        text=_ensure_suffix(default_file_name, file_suffix),
        placeholder=f"输入数据文件名称（默认 {file_suffix}）",
    )
    file_name = _ensure_suffix(file_name.strip(), file_suffix)
    if not ok or not file_name:
        return None
    return DataExportPlan(
        export_name=export_name,
        new_parent_id=selected_entry["node_id"],
        new_data_file_name=file_name,
    )


def choose_picture_export_plan(
    parent,
    *,
    title: str,
    default_export_name: str,
    preferred_target_node_id: Optional[str] = None,
    file_suffix: str = ".png",
) -> Optional[PictureExportPlan]:
    project = project_manager.current_project
    if project is None or project.tree is None:
        return None

    export_name, ok = TextInputDialog.get_text(
        parent,
        title,
        "图片名称:",
        text=_ensure_suffix(default_export_name, file_suffix),
        placeholder=f"输入图片名称（默认 {file_suffix}）",
    )
    export_name = _ensure_suffix(export_name.strip(), file_suffix)
    if not ok or not export_name:
        return None

    folder_entries = _build_picture_folder_entries()
    if not folder_entries:
        return None
    choice_entries = list(folder_entries)
    choice_entries.append({"label": "新建图片子文件夹...", "mode": "create_folder", "node_id": None})
    current_text = _preferred_target_label(choice_entries, project_manager.get_picture_target_folder_id(preferred_target_node_id))
    selected_label, ok = SelectionDialog.get_item(
        parent,
        title,
        "图片文件夹:",
        [entry["label"] for entry in choice_entries],
        current_text=current_text,
    )
    if not ok or not selected_label:
        return None
    selected_entry = next((entry for entry in choice_entries if entry["label"] == selected_label), None)
    if selected_entry is None:
        return None
    if selected_entry["mode"] == "folder":
        return PictureExportPlan(export_name=export_name, target_folder_id=selected_entry["node_id"])

    parent_label, ok = SelectionDialog.get_item(
        parent,
        "新建图片子文件夹",
        "父文件夹:",
        [entry["label"] for entry in folder_entries],
        current_text=current_text if current_text in [entry["label"] for entry in folder_entries] else None,
    )
    if not ok or not parent_label:
        return None
    parent_entry = next((entry for entry in folder_entries if entry["label"] == parent_label), None)
    if parent_entry is None:
        return None
    folder_name, ok = TextInputDialog.get_text(
        parent,
        "新建图片子文件夹",
        "文件夹名称:",
        placeholder="输入子文件夹名称",
    )
    folder_name = folder_name.strip()
    if not ok or not folder_name:
        return None
    folder = project_manager.add_folder(folder_name, parent_id=parent_entry["node_id"], group_type="pictures")
    if folder is None:
        return None
    return PictureExportPlan(export_name=export_name, target_folder_id=folder.id)


def _build_data_target_entries() -> List[dict]:
    project = project_manager.current_project
    if project is None or project.tree is None:
        return []
    entries: List[dict] = []
    for node in project.tree.nodes:
        if node.kind == "data_file":
            entries.append({
                "label": f"追加到数据文件 / {_node_path_label(node.id)}",
                "mode": "append",
                "node_id": node.id,
                "data_file_id": node.data_file_id,
            })
    for node in project.tree.nodes:
        if node.kind == "folder" and _node_belongs_to_group(node.id, "datasets"):
            entries.append({
                "label": f"新建数据文件 / {_node_path_label(node.id)}",
                "mode": "create_file",
                "node_id": node.id,
            })
    return entries


def _build_picture_folder_entries() -> List[dict]:
    project = project_manager.current_project
    if project is None or project.tree is None:
        return []
    entries: List[dict] = []
    for node in project.tree.nodes:
        if node.kind == "folder" and _node_belongs_to_group(node.id, "pictures"):
            entries.append({
                "label": _node_path_label(node.id),
                "mode": "folder",
                "node_id": node.id,
            })
    return entries


def _node_belongs_to_group(node_id: str, group_type: str) -> bool:
    project = project_manager.current_project
    if project is None or project.tree is None:
        return False
    current = project.tree.get_node(node_id)
    while current is not None:
        if current.kind == "folder":
            canonical = project_manager._canonical_group_type(getattr(current, "group_type", None))
            if canonical is not None:
                return canonical == group_type
        parent_id = getattr(current, "parent_id", None)
        current = project.tree.get_node(parent_id) if parent_id else None
    return False


def _node_path_label(node_id: str) -> str:
    project = project_manager.current_project
    if project is None or project.tree is None:
        return node_id
    parts: List[str] = []
    current = project.tree.get_node(node_id)
    while current is not None:
        parts.append(current.name)
        parent_id = getattr(current, "parent_id", None)
        current = project.tree.get_node(parent_id) if parent_id else None
    return " / ".join(reversed(parts)) if parts else node_id


def _preferred_target_label(entries: List[dict], preferred_node_id: Optional[str]) -> Optional[str]:
    if not preferred_node_id:
        return entries[0]["label"] if entries else None
    matched = next((entry["label"] for entry in entries if entry.get("node_id") == preferred_node_id), None)
    return matched or (entries[0]["label"] if entries else None)


def _ensure_suffix(name: str, suffix: str) -> str:
    value = (name or "").strip()
    if not value:
        return ""
    candidate = Path(value)
    if candidate.suffix.lower() == suffix.lower():
        return value
    if candidate.suffix:
        return candidate.with_suffix(suffix).name
    return f"{value}{suffix}"