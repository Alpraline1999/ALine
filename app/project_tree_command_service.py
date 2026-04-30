from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.project_manager import project_manager
from models.schemas import DataFile


@dataclass(slots=True)
class ProjectTreeCommandService:
    confirm_delete: Callable[[str, str], bool]
    confirm_batch_delete: Callable[[str, str], bool]
    choose_files: Callable[[str, str], list[str]]
    prompt_text: Callable[[str, str, str], tuple[str, bool]]
    prompt_existing_text: Callable[[str, str, str], tuple[str, bool]]
    choose_item: Callable[[str, str, list[str]], tuple[str, bool]]
    create_child_folder: Callable[[str, str], object | None]
    move_node_to_target: Callable[[str, str, str], bool]
    supports_digitize_import: Callable[[str], bool]
    linked_tree_node_id: Callable[[str, str, str], str | None]
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

    def move_virtual(self, kind: str, node_id: str, choices: list[tuple[str, str]]) -> None:
        labels = [label for label, _ in choices]
        selected, ok = self.choose_item("移动到", "目标父级:", labels)
        if not ok or not selected:
            return
        target_id = next((target_id for label, target_id in choices if label == selected), None)
        if target_id and self.move_node_to_target(kind, node_id, target_id):
            self.refresh()
            self.project_modified()
            return
        self.notify_warning("移动失败", self.last_error_message() or "目标位置已存在同名节点")

    def import_source_files(self, parent_id: str | None = None) -> None:
        clean_paths = [path for path in self.choose_files("导入源文件", "所有文件 (*.*)") if path]
        if not clean_paths:
            return
        nodes = project_manager.add_source_files(clean_paths, parent_id=parent_id, auto_rename_on_conflict=True)
        if not nodes:
            self.notify_warning("导入失败", self.last_error_message() or "未能导入任何源文件")
            return
        self.refresh()
        self.select_node(nodes[-1].id)
        self.project_modified()

    def import_digitize_images(self, parent_id: str | None = None) -> None:
        clean_paths = [
            path
            for path in self.choose_files(
                "导入图片到数字化",
                "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp);;所有文件 (*)",
            )
            if path
        ]
        if not clean_paths:
            return

        imported_node_ids: list[str] = []
        failed_paths: list[str] = []
        for path in clean_paths:
            if not self.supports_digitize_import(path):
                failed_paths.append(Path(path).name)
                continue
            try:
                image = project_manager.add_image(path, name=Path(path).name, parent_id=parent_id)
            except (FileNotFoundError, ValueError):
                failed_paths.append(Path(path).name)
                continue
            node_id = self.linked_tree_node_id("image_work", "image_work_id", image.id)
            if node_id:
                imported_node_ids.append(node_id)

        if not imported_node_ids:
            self.notify_warning("导入失败", self.last_error_message() or "未能导入任何图片")
            return

        self.refresh()
        self.select_node(imported_node_ids[-1])
        self.project_modified()
        self.notify_success("导入完成", f"已导入 {len(imported_node_ids)} 张图片到数字化")
        if failed_paths:
            self.notify_warning("部分导入失败", "以下图片未能导入: " + "、".join(failed_paths[:5]))
