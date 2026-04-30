from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from core.project_manager import project_manager
from models.schemas import DataFile


@dataclass(slots=True)
class ProjectTreeCommandService:
    confirm_delete: Callable[[str, str], bool]
    confirm_batch_delete: Callable[[str, str], bool]
    prompt_text: Callable[[str, str, str], tuple[str, bool]]
    prompt_existing_text: Callable[[str, str, str], tuple[str, bool]]
    choose_item: Callable[[str, str, list[str]], tuple[str, bool]]
    create_child_folder: Callable[[str, str], object | None]
    move_node_to_target: Callable[[str, str, str], bool]
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

    def delete_virtual(self, kind: str, node_id: str, node_name: str) -> None:
        if not self.confirm_delete("确认删除", f"确定要删除「{node_name}」吗？"):
            return
        if kind == "series":
            changed = project_manager.delete_series(node_id)
        else:
            changed = project_manager.delete_curve(node_id)
        if changed:
            self.refresh()
            self.project_modified()

    def delete_batch(self, payloads: list[dict[str, object]]) -> None:
        count = len(payloads)
        names = [str(item["name"]) for item in payloads[:5]]
        summary = "\n".join(f"- {name}" for name in names)
        if count > 5:
            summary += f"\n- ... 另有 {count - 5} 项"
        if not self.confirm_batch_delete("确认批量删除", f"确定要删除选中的 {count} 项吗？\n\n{summary}"):
            return

        changed = False
        for payload in payloads:
            kind = str(payload["kind"])
            node_id = str(payload["node_id"])
            if kind == "series":
                changed = project_manager.delete_series(node_id) or changed
            elif kind == "curve":
                changed = project_manager.delete_curve(node_id) or changed
            else:
                changed = project_manager.delete_node(node_id) or changed
        if changed:
            self.refresh()
            self.project_modified()

    def move_batch(self, payloads: list[dict[str, object]], choices: list[tuple[str, str]]) -> None:
        labels = [label for label, _ in choices]
        selected, ok = self.choose_item("批量移动到", "目标父级:", labels)
        if not ok or not selected:
            return
        target_id = next((target_id for label, target_id in choices if label == selected), None)
        if target_id is None:
            return

        changed = False
        failed = 0
        for payload in payloads:
            moved = self.move_node_to_target(str(payload["kind"]), str(payload["node_id"]), target_id)
            changed = moved or changed
            if not moved:
                failed += 1
        if changed:
            self.refresh()
            self.project_modified()
        if failed:
            self.notify_warning("批量移动未完成", self.last_error_message() or f"有 {failed} 项移动失败")
