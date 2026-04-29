from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from core.project_manager import project_manager
from models.schemas import DataFile


@dataclass(slots=True)
class ProjectTreeCommandService:
    confirm_delete: Callable[[str, str], bool]
    prompt_text: Callable[[str, str, str], tuple[str, bool]]
    create_child_folder: Callable[[str, str], object | None]
    notify_warning: Callable[[str, str], None]
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
