from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from core.project_manager import project_manager
from models.schemas import DataFile


@dataclass(slots=True)
class ProjectTreeCommandService:
    confirm_delete: Callable[[str, str], bool]
    prompt_text: Callable[[str, str, str], tuple[str, bool]]
    prompt_existing_text: Callable[[str, str, str], tuple[str, bool]]
    create_child_folder: Callable[[str, str], object | None]
    notify_warning: Callable[[str, str], None]
    notify_success: Callable[[str, str], None]
    refresh: Callable[[], None]
    select_node: Callable[[str], None]
    project_modified: Callable[[], None]
    last_error_message: Callable[[], str]

    def delete_node(self, node_id: str, node_name: str) -> None:
        if not self.confirm_delete("确认删除", f"确定要删除「{node_name}」及其所有内容吗？"):
            return
        project_manager.delete_node(node_id)
        self.refresh()
        self.project_modified()

    def add_child_folder(self, parent_id: str) -> None:
        name, ok = self.prompt_text("新建子文件夹", "文件夹名称:", "输入子文件夹名称")
        if not ok:
            return
        folder = self.create_child_folder(parent_id, name)
        if folder is None:
            self.notify_warning("创建失败", self.last_error_message() or "未能创建子文件夹")
            return
        self.refresh()
        self.select_node(folder.id)
        self.project_modified()

    def add_dataset_node(self, parent_id: str) -> None:
        name, ok = self.prompt_text("新建数据集", "数据集名称:", "输入数据集名称")
        if not ok:
            return
        clean_name = name.strip()
        if not clean_name:
            return
        node = project_manager.add_data_file(DataFile(name=clean_name), parent_id=parent_id)
        if node is None:
            self.notify_warning("创建失败", self.last_error_message() or "未能创建新的数据集")
            return
        self.refresh()
        self.select_node(node.id)
        self.project_modified()

    def rename_virtual(self, kind: str, node_id: str, current_name: str) -> None:
        title = "重命名数据列" if kind == "series" else "重命名曲线"
        new_name, ok = self.prompt_existing_text(title, "名称:", current_name)
        if not ok or not new_name.strip():
            return
        if kind == "series":
            changed = project_manager.rename_series(node_id, new_name.strip())
        else:
            changed = project_manager.rename_curve(node_id, new_name.strip())
        if changed:
            self.refresh()
            self.project_modified()
            return
        self.notify_warning("重命名失败", self.last_error_message() or "名称已存在或当前节点不支持重命名")

    def prune_empty_folders(self, root_id: str | None = None, *, scope_label: str = "项目树") -> None:
        removed_ids = project_manager.remove_empty_folders(root_id)
        if not removed_ids:
            self.notify_success("无需清理", f"{scope_label} 中没有可移除的空文件夹")
            return
        self.refresh()
        self.project_modified()
        self.notify_success("清理完成", f"已移除 {len(removed_ids)} 个空文件夹")
