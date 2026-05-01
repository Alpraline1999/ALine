"""
DataPage 待导入队列协调器 — 处理批次导入逻辑。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from qfluentwidgets import InfoBar, InfoBarPosition


class DataPagePendingImportCoordinator:
    """DataPage 待导入排队与批次执行协调器。

    通过回调注入访问 DataPage 的状态与 UI 控制方法。
    """

    def __init__(
        self,
        *,
        # 状态访问
        get_pending_import_paths,
        get_pending_import_names,
        get_pending_import_states,
        # 状态变更
        remove_pending_source_files,
        refresh,
        project_modified,
        # 导入工具方法
        create_import_dialog,
        apply_import_dialog_results,
        on_tree_node_selected,
        # 当前上下文
        current_import_group,
        current_selection,
        dialog_parent,
    ):
        self._get_paths = get_pending_import_paths
        self._get_names = get_pending_import_names
        self._get_states = get_pending_import_states
        self._remove_pending = remove_pending_source_files
        self._refresh = refresh
        self._project_modified = project_modified
        self._create_dialog = create_import_dialog
        self._apply_results = apply_import_dialog_results
        self._on_selected = on_tree_node_selected
        self._current_group = current_import_group
        self._current_selection = current_selection
        self._dialog_parent = dialog_parent

    def import_pending_files_for_current_group(self) -> None:
        """根据当前分组类型执行对应的批次导入。"""
        group_type = self._current_group()
        if group_type == "datasets":
            self._import_pending_source_files_to_datasets()
        elif group_type == "images":
            self._import_pending_source_files_to_digitize()
        elif group_type == "source_files":
            self._import_pending_files_as_source_files()

    def _import_pending_source_files_to_datasets(self) -> None:
        paths = self._get_paths()
        if not paths:
            return

        completed_paths: list[str] = []
        failed_names: list[str] = []
        stopped = False
        sel = self._current_selection()

        for file_path in list(paths):
            path = Path(file_path)
            import_name = self._get_names().get(file_path, path.name)
            if not path.exists():
                failed_names.append(import_name)
                continue
            try:
                dialog = self._create_dialog(str(path), default_file_name=import_name)
            except Exception as exc:
                failed_names.append(import_name)
                InfoBar.warning("导入失败", f"无法读取文件 {path.name}: {exc}", parent=self._dialog_parent(), position=InfoBarPosition.TOP)
                continue
            if not dialog.exec():
                stopped = True
                break
            if self._apply_results(dialog, show_feedback=False):
                completed_paths.append(str(path))
            else:
                failed_names.append(import_name)

        if completed_paths:
            self._remove_pending(completed_paths)
            self._project_modified()
            self._refresh()
            if sel[0] and sel[1]:
                self._on_selected(sel[0], sel[1])

        summary = f"成功导入 {len(completed_paths)} 个文件到数据集"
        if failed_names:
            summary += f"，失败 {len(failed_names)} 个"
        if stopped:
            summary += "，导入在中途停止"
        if completed_paths:
            InfoBar.success("批量导入完成", summary, parent=self._dialog_parent(), position=InfoBarPosition.TOP)
        elif failed_names or stopped:
            InfoBar.warning("批量导入未完成", summary, parent=self._dialog_parent(), position=InfoBarPosition.TOP)

    def _import_pending_source_files_to_digitize(self) -> None:
        paths = self._get_paths()
        if not paths:
            return

        completed_paths: list[str] = []
        failed_names: list[str] = []
        sel = self._current_selection()

        for file_path in list(paths):
            path = Path(file_path)
            import_name = self._get_names().get(file_path, path.name)
            if not path.exists():
                failed_names.append(import_name)
                continue
            try:
                from ui.dialogs.import_dialog import ImportDialog

                dialog = ImportDialog(self._dialog_parent())
                dialog.load_file(str(path))
            except Exception as exc:
                failed_names.append(import_name)
                InfoBar.warning("导入失败", f"无法读取图片 {path.name}: {exc}", parent=self._dialog_parent(), position=InfoBarPosition.TOP)
                continue

            if not dialog.exec():
                continue

            series_list = dialog.get_results()
            if not series_list:
                continue

            from core.project_manager import project_manager

            image_path = path
            if not isinstance(image_path, str):
                image_path = str(image_path)

            try:
                image = project_manager.add_image(image_path, name=import_name, parent_id=self._current_group_target_id())
            except (FileNotFoundError, ValueError) as exc:
                failed_names.append(import_name)
                InfoBar.warning("导入失败", f"无法导入图片 {import_name}: {exc}", parent=self._dialog_parent(), position=InfoBarPosition.TOP)
                continue

            for series in series_list:
                project_manager.add_curve_to_image(image.id, series)

            completed_paths.append(str(path))

        if completed_paths:
            self._remove_pending(completed_paths)
            self._refresh()
            self._project_modified()
            if sel[0] and sel[1]:
                self._on_selected(sel[0], sel[1])

        summary = f"成功导入 {len(completed_paths)} 个文件到数字化"
        if failed_names:
            summary += f"，失败 {len(failed_names)} 个"
        if completed_paths:
            InfoBar.success("批量导入完成", summary, parent=self._dialog_parent(), position=InfoBarPosition.TOP)
        elif failed_names:
            InfoBar.warning("批量导入未完成", summary, parent=self._dialog_parent(), position=InfoBarPosition.TOP)

    def _import_pending_files_as_source_files(self) -> None:
        paths = self._get_paths()
        if not paths:
            return

        from core.project_manager import project_manager

        completed_paths: list[str] = []
        failed_names: list[str] = []
        sel = self._current_selection()

        for file_path in list(paths):
            path = Path(file_path)
            import_name = self._get_names().get(file_path, path.name)
            if not path.exists():
                failed_names.append(import_name)
                continue
            import_path = str(path)
            nodes = project_manager.add_source_files([import_path], parent_id=self._current_group_target_id(), auto_rename_on_conflict=True)
            if nodes:
                completed_paths.append(import_path)
            else:
                failed_names.append(import_name)

        if completed_paths:
            self._remove_pending(completed_paths)
            self._refresh()
            self._project_modified()
            if sel[0] and sel[1]:
                self._on_selected(sel[0], sel[1])

        summary = f"成功导入 {len(completed_paths)} 个源文件"
        if failed_names:
            summary += f"，失败 {len(failed_names)} 个"
        if completed_paths:
            InfoBar.success("批量导入完成", summary, parent=self._dialog_parent(), position=InfoBarPosition.TOP)
        elif failed_names:
            InfoBar.warning("批量导入未完成", summary, parent=self._dialog_parent(), position=InfoBarPosition.TOP)

    def _current_group_target_id(self) -> Optional[str]:
        """获取当前导入分组的目标文件夹 ID。"""
        from ui.pages.data_page import DataPage
        return None  # 由 DataPage 根据当前选中节点解析目标 ID
