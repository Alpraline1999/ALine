from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtWidgets import QWidget

from core.global_assets import global_assets, parse_plot_style_asset_key
from core.project_manager import project_manager
from models.schemas import DataFile
from ui.dialogs.node_remark_dialog import NodeRemarkDialog


@dataclass(slots=True)
class ProjectTreeCommandService:
    confirm_delete: Callable[[str, str], bool]
    confirm_batch_delete: Callable[[str, str], bool]
    choose_file: Callable[[str, str], str]
    choose_files: Callable[[str, str], list[str]]
    prompt_text: Callable[[str, str, str], tuple[str, bool]]
    prompt_existing_text: Callable[[str, str, str], tuple[str, bool]]
    choose_item: Callable[[str, str, list[str]], tuple[str, bool]]
    create_child_folder: Callable[[str, str], object | None]
    create_source_file_import_dialog: Callable[[str], object]
    configure_source_file_import_target: Callable[[object, str | None], None]
    move_node_to_target: Callable[[str, str, str], bool]
    supports_data_file_import: Callable[[str], bool]
    supports_digitize_import: Callable[[str], bool]
    linked_tree_node_id: Callable[[str, str, str], str | None]
    notify_warning: Callable[[str, str], None]
    notify_success: Callable[[str, str], None]
    dialog_parent: Callable[[], QWidget]
    refresh: Callable[[], None]
    select_node: Callable[[str], None]
    project_modified: Callable[[], None]
    last_error_message: Callable[[], str]

    def _resolve_project_id_for_node(self, node_id: str | None) -> str | None:
        if not node_id:
            return None
        finder = getattr(project_manager, "find_project_containing_node", None)
        if not callable(finder):
            return None
        project = finder(node_id)
        return None if project is None else getattr(project, "id", None)

    def _activate_project(self, project_id: str | None = None, *, node_id: str | None = None, parent_id: str | None = None) -> None:
        resolved = project_id
        if resolved:
            if not project_manager.get_project(resolved):
                resolved = None
        if not resolved:
            resolved = self._resolve_project_id_for_node(node_id) or self._resolve_project_id_for_node(parent_id)
        if resolved:
            project_manager.set_current_project(resolved)

    def delete_node(self, node_id: str, node_name: str, *, project_id: str | None = None) -> None:
        self._activate_project(project_id, node_id=node_id)
        if not self.confirm_delete("确认删除", f"确定要删除「{node_name}」及其所有内容吗？"):
            return
        if not project_manager.delete_node(node_id):
            self.notify_warning("删除失败", self.last_error_message() or "当前节点不存在或无法删除")
            return
        self.refresh()
        self.project_modified()

    def add_child_folder(self, parent_id: str, *, project_id: str | None = None) -> None:
        self._activate_project(project_id, node_id=parent_id)
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

    def add_dataset_node(self, parent_id: str, *, project_id: str | None = None) -> None:
        self._activate_project(project_id, node_id=parent_id)
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
        self._activate_project(None, node_id=node_id)
        title = "重命名数据列" if kind == "series" else "重命名曲线"
        new_name, ok = self.prompt_existing_text(title, "名称:", current_name)
        if not ok or not new_name.strip():
            return
        changed = self.rename_node_by_kind(kind, node_id, new_name.strip())
        if changed:
            self.refresh()
            self.project_modified()
            return
        self.notify_warning("重命名失败", self.last_error_message() or "名称已存在或当前节点不支持重命名")

    def rename_selected_item(self, kind: str, node_id: str, current_name: str, *, project_id: str | None = None) -> bool:
        self._activate_project(project_id, node_id=node_id)
        title_map = {
            "folder": "重命名文件夹",
            "data_file": "重命名数据文件",
            "source_file": "重命名源文件",
            "image_work": "重命名图像",
            "picture": "重命名图片",
            "analysis_result": "重命名分析结果",
            "series": "重命名数据列",
            "curve": "重命名曲线",
        }
        new_name, ok = self.prompt_existing_text(title_map.get(kind, "重命名节点"), "名称:", current_name)
        if not ok or not new_name.strip():
            return False
        changed = self.rename_global_asset(kind, node_id, new_name) if kind.startswith("global_") else self.rename_node_by_kind(kind, node_id, new_name.strip())
        if not changed:
            self.notify_warning("重命名失败", self.last_error_message() or "名称已存在或当前节点不支持重命名")
            return False
        self.refresh()
        self.select_node(node_id)
        self.project_modified()
        return True

    def edit_selected_item_remark(self, kind: str, node_id: str, current_name: str, current_remark: str = "", *, project_id: str | None = None) -> bool:
        self._activate_project(project_id, node_id=node_id)
        if kind.startswith("global_") or kind == "project":
            return False
        title_map = {
            "folder": "设置备注",
            "data_file": "设置备注",
            "source_file": "设置备注",
            "image_work": "设置备注",
            "picture": "设置备注",
            "analysis_result": "设置备注",
            "series": "设置备注",
            "curve": "设置备注",
        }
        remark, ok = NodeRemarkDialog.get_remark(
            self.dialog_parent(),
            f"{title_map.get(kind, '设置备注')} · {current_name or node_id}",
            remark=current_remark,
        )
        if not ok:
            return False
        changed = self.update_node_remark(kind, node_id, remark)
        if not changed:
            self.notify_warning("编辑备注失败", self.last_error_message() or "当前节点不支持备注编辑")
            return False
        self.refresh()
        self.select_node(node_id)
        self.project_modified()
        return True

    def rename_node_by_kind(self, kind: str, node_id: str, new_name: str) -> bool:
        clean_name = new_name.strip()
        if not clean_name:
            return False
        if kind == "series":
            return project_manager.rename_series(node_id, clean_name)
        if kind == "curve":
            return project_manager.rename_curve(node_id, clean_name)
        return project_manager.rename_node(node_id, clean_name)

    def prune_empty_folders(self, root_id: str | None = None, *, scope_label: str = "项目树") -> bool:
        removed_ids = project_manager.remove_empty_folders(root_id)
        if not removed_ids:
            self.notify_success("无需清理", f"{scope_label} 中没有可移除的空文件夹")
            return False
        self.refresh()
        self.project_modified()
        self.notify_success("清理完成", f"已移除 {len(removed_ids)} 个空文件夹")
        return True

    def delete_virtual(self, kind: str, node_id: str, node_name: str, *, project_id: str | None = None) -> None:
        self._activate_project(project_id, node_id=node_id)
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
        if payloads:
            self._activate_project(None, node_id=str(payloads[0].get("node_id", "")))
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
        if payloads:
            self._activate_project(None, node_id=str(payloads[0].get("node_id", "")))
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

    def move_virtual(self, kind: str, node_id: str, choices: list[tuple[str, str]], *, project_id: str | None = None) -> None:
        self._activate_project(project_id, node_id=node_id)
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

    def can_edit_global_asset(self, kind: str, node_id: str) -> bool:
        if kind == "global_report_template":
            item = global_assets.get_report_template(node_id)
            return bool(item is not None and not item.is_builtin)
        if kind == "global_curve_style_template":
            item = global_assets.get_curve_style_template(node_id)
            return bool(item is not None and not item.is_builtin)
        if kind == "global_plot_style":
            style_type, asset_id = parse_plot_style_asset_key(node_id)
            return global_assets.get_figure_template(asset_id) is not None
        if kind == "global_extension_config":
            item = global_assets.get_extension_config(node_id)
            return bool(item is not None and not item.is_default)
        return kind in {
            "global_pipeline",
            "global_plot_pipeline",
            "global_ai_prompt",
            "global_ai_skill",
            "global_ai_agent",
        }

    def rename_global_asset(self, kind: str, node_id: str, new_name: str) -> bool:
        clean_name = new_name.strip()
        if not clean_name or not self.can_edit_global_asset(kind, node_id):
            return False
        if kind == "global_pipeline":
            return global_assets.update_saved_pipeline(node_id, name=clean_name)
        if kind == "global_plot_pipeline":
            return global_assets.update_saved_plot_pipeline(node_id, name=clean_name)
        if kind == "global_report_template":
            return global_assets.update_report_template(node_id, name=clean_name)
        if kind == "global_curve_style_template":
            return global_assets.update_curve_style_template(node_id, name=clean_name)
        if kind == "global_plot_style":
            style_type, asset_id = parse_plot_style_asset_key(node_id)
            return global_assets.update_figure_template(asset_id, name=clean_name)
        if kind == "global_extension_config":
            return global_assets.update_extension_config(node_id, name=clean_name) is not None
        if kind == "global_ai_prompt":
            return global_assets.update_ai_prompt(node_id, name=clean_name)
        if kind == "global_ai_skill":
            return global_assets.update_ai_skill(node_id, name=clean_name)
        if kind == "global_ai_agent":
            return global_assets.update_ai_agent(node_id, name=clean_name)
        return False

    def delete_global_asset(self, kind: str, node_id: str) -> bool:
        if not self.can_edit_global_asset(kind, node_id):
            return False
        if kind == "global_pipeline":
            return global_assets.delete_saved_pipeline(node_id)
        if kind == "global_plot_pipeline":
            return global_assets.delete_saved_plot_pipeline(node_id)
        if kind == "global_report_template":
            return global_assets.delete_report_template(node_id)
        if kind == "global_curve_style_template":
            return global_assets.delete_curve_style_template(node_id)
        if kind == "global_plot_style":
            style_type, asset_id = parse_plot_style_asset_key(node_id)
            return global_assets.delete_figure_template(asset_id)
        if kind == "global_extension_config":
            return global_assets.delete_extension_config(node_id)
        if kind == "global_ai_prompt":
            return global_assets.delete_ai_prompt(node_id)
        if kind == "global_ai_skill":
            return global_assets.delete_ai_skill(node_id)
        if kind == "global_ai_agent":
            return global_assets.delete_ai_agent(node_id)
        return False

    def update_node_remark(self, kind: str, node_id: str, remark: str) -> bool:
        if kind == "series":
            return project_manager.set_series_remark(node_id, remark)
        if kind == "curve":
            return project_manager.set_curve_remark(node_id, remark)
        if kind == "analysis_result":
            return project_manager.set_analysis_result_remark(node_id, remark)
        return project_manager.set_node_remark(node_id, remark)

    def get_node_remark(self, kind: str, node_id: str) -> str:
        if kind == "series":
            return project_manager.get_series_remark(node_id)
        if kind == "curve":
            return project_manager.get_curve_remark(node_id)
        if kind == "analysis_result":
            return project_manager.get_analysis_result_remark(node_id)
        return project_manager.get_node_remark(node_id)

    def rename_global(self, kind: str, node_id: str, current_name: str) -> None:
        new_name, ok = self.prompt_existing_text("重命名全局资源", "名称:", current_name)
        if not ok:
            return
        if self.rename_global_asset(kind, node_id, new_name):
            self.refresh()
            self.project_modified()

    def delete_global(self, kind: str, node_id: str, node_name: str) -> None:
        if not self.confirm_delete("确认删除", f"确定要删除全局资源「{node_name}」吗？"):
            return
        if self.delete_global_asset(kind, node_id):
            self.refresh()
            self.project_modified()

    def import_source_files(self, parent_id: str | None = None, *, project_id: str | None = None) -> None:
        self._activate_project(project_id, node_id=parent_id)
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

    def import_digitize_images(self, parent_id: str | None = None, *, project_id: str | None = None) -> None:
        self._activate_project(project_id, node_id=parent_id)
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

    def import_source_file_as_digitize_image(
        self,
        source_path: str,
        *,
        parent_id: str | None = None,
        display_name: str | None = None,
        project_id: str | None = None,
    ) -> str | None:
        self._activate_project(project_id, node_id=parent_id)
        if not self.supports_digitize_import(source_path):
            return None
        try:
            image = project_manager.add_image(source_path, name=display_name or Path(source_path).name, parent_id=parent_id)
        except (FileNotFoundError, ValueError):
            self.notify_warning("导入失败", self.last_error_message() or "未能导入图片到数字化")
            return None
        return self.linked_tree_node_id("image_work", "image_work_id", image.id)

    def import_data_file(self, parent_id: str | None = None, *, project_id: str | None = None) -> None:
        self._activate_project(project_id, node_id=parent_id)
        file_path = self.choose_file(
            "导入数据文件",
            "数据文件 (*.csv *.txt *.dat *.tsv *.xlsx *.xls *.json *.npy *.npz);;所有文件 (*)",
        )
        if not file_path:
            return
        selected_node_id = self.import_source_file_as_dataset(file_path, target_folder_id=parent_id)
        if not selected_node_id:
            return
        self.refresh()
        self.select_node(selected_node_id)
        self.project_modified()

    def import_source_file_as_dataset(
        self,
        source_path: str,
        *,
        target_folder_id: str | None = None,
        target_data_file_id: str | None = None,
        project_id: str | None = None,
    ) -> str | None:
        self._activate_project(project_id, node_id=target_data_file_id, parent_id=target_folder_id)
        if not self.supports_data_file_import(source_path):
            self.notify_warning("导入失败", "当前文件类型不支持导入为数据文件")
            return None
        try:
            dialog = self.create_source_file_import_dialog(source_path)
        except Exception as exc:
            self.notify_warning("导入失败", f"无法读取文件: {exc}")
            return None
        self.configure_source_file_import_target(dialog, target_data_file_id)
        if not dialog.exec():
            return None
        return self._apply_source_file_import_dialog_results(
            dialog,
            target_folder_id=target_folder_id,
            target_data_file_id=target_data_file_id,
        )

    def _apply_source_file_import_dialog_results(
        self,
        dialog: object,
        *,
        target_folder_id: str | None = None,
        target_data_file_id: str | None = None,
    ) -> str | None:
        self._activate_project(None, node_id=target_data_file_id, parent_id=target_folder_id)
        series_list = dialog.get_results()
        if not series_list:
            return None

        if target_data_file_id:
            data_file = project_manager.get_data_file(target_data_file_id)
            if data_file is None:
                self.notify_warning("导入失败", "所选目标数据文件不存在")
                return None
            appended = 0
            for series in series_list:
                if project_manager.add_series_to_data_file(target_data_file_id, series):
                    appended += 1
            if appended != len(series_list):
                self.notify_warning("导入失败", self.last_error_message() or "部分数据系列追加失败")
                return None
            self.notify_success("导入成功", f"已导入 {len(series_list)} 条数据系列到数据文件 {data_file.name}")
            return self.linked_tree_node_id("data_file", "data_file_id", target_data_file_id)

        source_path = dialog.get_source_path() if hasattr(dialog, "get_source_path") else ""
        if not isinstance(source_path, str):
            source_path = ""
        data_file = DataFile(
            name=dialog.get_file_name(),
            source_path=source_path,
            series=series_list,
        )
        node = project_manager.add_data_file(data_file, parent_id=target_folder_id, auto_rename_on_conflict=True)
        if node is None:
            self.notify_warning("导入失败", self.last_error_message() or "未能创建新的数据文件")
            return None
        self.notify_success("导入成功", f"已导入 {len(series_list)} 条数据系列到数据文件 {data_file.name}")
        return node.id
