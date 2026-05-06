"""
ProjectTreeWidget 右键菜单构建与命令执行。
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidgetItem
from qfluentwidgets import Action, FluentIcon as FIF, RoundMenu

from core.extension_api import build_extension_entry, extension_registry
from core.global_assets import global_assets
from core.project_manager import project_manager


class ProjectTreeMenuBuilder:
    """ProjectTreeWidget 的右键菜单构建与命令执行辅助。"""

    def __init__(
        self,
        *,
        tree_widget: object,
        add_menu_action: Callable,
        append_menu_section: Callable,
        append_tree_scope_actions: Callable,
        batch_action_payloads: Callable,
        common_batch_move_choices: Callable,
        command_service: object,
        page_dispatcher: object,
        dialog_parent: Callable,
        refresh: Callable,
        select_node: Callable,
        project_modified: Callable,
        tree_view: object,
        selected_items_for_context_menu: Callable,
        move_target_choices: Callable,
        move_node_to_target: Callable,
        is_protected_folder: Callable,
        folder_collection_group: Callable,
        is_focus_active: Callable,
        focus_selected_item: Callable,
        clear_focus: Callable,
        rename_selected_item: Callable,
        can_edit_global_asset: Callable,
        _extension_config_sort_key: Callable,
        _parse_extension_config_group_node_id: Callable,
        _cmd_create_extension_config: Callable,
        _cmd_duplicate_extension_config: Callable,
        _cmd_export_extension_config: Callable,
        _cmd_set_default_extension_config: Callable,
        _cmd_delete: Callable,
        _cmd_delete_batch: Callable,
        _cmd_delete_virtual: Callable,
        _cmd_delete_global: Callable,
        _cmd_add_child_folder: Callable,
        _cmd_add_dataset_node: Callable,
        _cmd_import_data_file: Callable,
        _cmd_import_source_files: Callable,
        _cmd_import_digitize_images: Callable,
        _cmd_rename_global: Callable,
        _cmd_prune_empty_folders: Callable,
        _cmd_move_batch: Callable,
        _cmd_move_virtual: Callable,
        _open_picture_folder: Callable,
        _open_source_file_folder: Callable,
        save_current_project: Callable,
        save_current_project_as: Callable,
        close_current_project: Callable,
        _SYNTHETIC_GLOBAL_KINDS: frozenset,
        _MANAGED_FOLDER_GROUP_TYPES: frozenset,
        _PICTURE_GROUP_ICON: object,
        _SOURCE_FOLDER_ICON: object,
        _NEW_DATASET_ACTION_ICON: object,
        _IMPORT_DATA_ACTION_ICON: object,
        _OPEN_DIGITIZE_ACTION_ICON: object,
        _PICTURE_GROUP_ICON_v2: object,
    ):
        self._tree_widget = tree_widget
        self._add_menu_action = add_menu_action
        self._append_menu_section = append_menu_section
        self._append_tree_scope_actions = append_tree_scope_actions
        self._batch_action_payloads = batch_action_payloads
        self._common_batch_move_choices = common_batch_move_choices
        self._command_service = command_service
        self._page_dispatcher = page_dispatcher
        self._dialog_parent = dialog_parent
        self._refresh = refresh
        self._select_node = select_node
        self._project_modified = project_modified
        self._tree = tree_view
        self._selected_items_for_context_menu = selected_items_for_context_menu
        self._move_target_choices = move_target_choices
        self._move_node_to_target = move_node_to_target
        self._is_protected_folder = is_protected_folder
        self._folder_collection_group = folder_collection_group
        self._is_focus_active = is_focus_active
        self._focus_selected_item = focus_selected_item
        self._clear_focus = clear_focus
        self._rename_selected_item = rename_selected_item
        self._can_edit_global_asset = can_edit_global_asset
        self._extension_config_sort_key = _extension_config_sort_key
        self._parse_extension_config_group_node_id = _parse_extension_config_group_node_id
        self._cmd_create_extension_config = _cmd_create_extension_config
        self._cmd_duplicate_extension_config = _cmd_duplicate_extension_config
        self._cmd_export_extension_config = _cmd_export_extension_config
        self._cmd_set_default_extension_config = _cmd_set_default_extension_config
        self._cmd_delete = _cmd_delete
        self._cmd_delete_batch = _cmd_delete_batch
        self._cmd_delete_virtual = _cmd_delete_virtual
        self._cmd_delete_global = _cmd_delete_global
        self._cmd_add_child_folder = _cmd_add_child_folder
        self._cmd_add_dataset_node = _cmd_add_dataset_node
        self._cmd_import_data_file = _cmd_import_data_file
        self._cmd_import_source_files = _cmd_import_source_files
        self._cmd_import_digitize_images = _cmd_import_digitize_images
        self._cmd_rename_global = _cmd_rename_global
        self._cmd_prune_empty_folders = _cmd_prune_empty_folders
        self._cmd_move_batch = _cmd_move_batch
        self._cmd_move_virtual = _cmd_move_virtual
        self._open_picture_folder = _open_picture_folder
        self._open_source_file_folder = _open_source_file_folder
        self._save_current_project = save_current_project
        self._save_current_project_as = save_current_project_as
        self._close_current_project = close_current_project
        self._SYNTHETIC_GLOBAL_KINDS = _SYNTHETIC_GLOBAL_KINDS
        self._MANAGED_FOLDER_GROUP_TYPES = _MANAGED_FOLDER_GROUP_TYPES
        self._PICTURE_GROUP_ICON = _PICTURE_GROUP_ICON
        self._SOURCE_FOLDER_ICON = _SOURCE_FOLDER_ICON
        self._NEW_DATASET_ACTION_ICON = _NEW_DATASET_ACTION_ICON
        self._IMPORT_DATA_ACTION_ICON = _IMPORT_DATA_ACTION_ICON
        self._OPEN_DIGITIZE_ACTION_ICON = _OPEN_DIGITIZE_ACTION_ICON

    def build_context_menu(self, pos) -> None:
        """在 tree view 的 pos 处构建并执行右键菜单。"""
        item = self._tree.itemAt(pos)
        if item is None:
            menu = RoundMenu(parent=self._dialog_parent())
            focus_items = (
                list(self._tree_widget._selected_items_or_current())
                if hasattr(self._tree_widget, "_selected_items_or_current")
                else []
            )
            project_id = (
                self._tree_widget._resolve_scope_project_id(items=focus_items)
                if hasattr(self._tree_widget, "_resolve_scope_project_id")
                else None
            )
            self._append_tree_scope_actions(menu, focus_items=focus_items, project_id=project_id)
            menu.exec(self._tree.viewport().mapToGlobal(pos))
            return

        selected_items = self._selected_items_for_context_menu(item)
        # activate the project context
        self._activate_item_project(item)
        menu = RoundMenu(parent=self._dialog_parent())
        import_entries: list[tuple[object, str, object]] = []
        manage_entries: list[tuple[object, str, object]] = []

        batch_payloads = self._batch_action_payloads(selected_items)
        if len(batch_payloads) > 1:
            self._build_batch_menu(menu, batch_payloads, selected_items, pos)
            return

        d = self._item_role_data(item)
        if not d:
            return
        kind, node_id = d

        if kind == "project":
            manage_entries.extend([
                (FIF.SAVE, "保存项目", self._save_current_project),
                (FIF.SAVE, "另存项目", self._save_current_project_as),
                (FIF.CLOSE, "关闭项目", self._close_current_project),
            ])
            self._append_menu_section(menu, manage_entries)
            self._append_tree_scope_actions(
                menu,
                separated=True,
                focus_items=selected_items,
                project_id=self._item_project_id(item),
            )
            menu.exec(self._tree.viewport().mapToGlobal(pos))
            return

        if kind in self._SYNTHETIC_GLOBAL_KINDS:
            self._build_global_kind_menu(menu, pos, kind, node_id, item, manage_entries)
            return

        self._build_node_menu(
            kind, node_id, item,
            import_entries, manage_entries,
        )

        self._append_menu_section(menu, import_entries)
        self._append_menu_section(menu, manage_entries)

        if menu.actions():
            self._append_tree_scope_actions(
                menu,
                separated=True,
                focus_items=selected_items,
                project_id=self._item_project_id(item),
            )
            menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _activate_item_project(self, item: Optional[QTreeWidgetItem]) -> None:
        if item is None:
            return
        project_id = self._item_project_id(item)
        if project_id:
            project_manager.set_current_project(project_id)

    def _item_role_data(self, item: Optional[QTreeWidgetItem]) -> Optional[tuple[str, str]]:
        if item is None:
            return None
        d = item.data(0, Qt.ItemDataRole.UserRole)
        if d:
            return d[0], d[1]
        return None

    def _item_project_id(self, item: Optional[QTreeWidgetItem]) -> Optional[str]:
        if item is None:
            return None
        project_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if project_id:
            return project_id
        parent = item.parent()
        if parent is not None:
            return self._item_project_id(parent)
        return None

    def _build_batch_menu(self, menu: RoundMenu, batch_payloads: list[dict[str, object]], selected_items: list[QTreeWidgetItem], pos) -> None:
        focus_entries: list[tuple[object, str, object]] = []
        focus_keys = set(self._tree_widget.focused_item_keys()) if hasattr(self._tree_widget, "focused_item_keys") else set()
        selected_key_list = list(self._tree_widget._selected_item_keys(selected_items)) if hasattr(self._tree_widget, "_selected_item_keys") else []
        selected_keys = set(selected_key_list)
        if focus_keys and (not selected_keys or selected_keys == focus_keys):
            focus_entries.append((getattr(FIF, "CANCEL", FIF.CLOSE), "退出专注", self._clear_focus))
        elif selected_items:
            label = "切换专注到所选" if self._tree_widget.is_focus_active() else "专注所选"
            focus_entries.append(
                (
                    getattr(FIF, "PIN", getattr(FIF, "VIEW", FIF.SEARCH)),
                    label,
                    lambda keys=list(selected_key_list): self._tree_widget.focus_item_keys(keys),
                )
            )
        manage_entries = [
            (FIF.DELETE, f"删除选中 {len(batch_payloads)} 项", lambda: self._cmd_delete_batch(batch_payloads)),
        ]
        move_choices = self._common_batch_move_choices(batch_payloads)
        if move_choices:
            manage_entries.append(
                (FIF.SYNC, f"移动选中 {len(batch_payloads)} 项...", lambda: self._cmd_move_batch(batch_payloads, move_choices))
            )
        self._append_menu_section(menu, focus_entries)
        self._append_menu_section(menu, manage_entries)
        self._append_tree_scope_actions(
            menu,
            separated=True,
            focus_items=selected_items,
            project_id=self._item_project_id(selected_items[0]) if selected_items else None,
        )
        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _build_global_kind_menu(self, menu: RoundMenu, pos, kind: str, node_id: str, item, manage_entries: list) -> None:
        if kind == "global_pipeline":
            manage_entries.append((FIF.DEVELOPER_TOOLS, "加载到处理页", self._page_dispatcher.make_activation_callback(kind, node_id)))
        elif kind == "global_report_template":
            manage_entries.append((FIF.DOCUMENT, "应用到分析页", self._page_dispatcher.make_activation_callback(kind, node_id)))
        elif kind == "global_curve_style_template":
            manage_entries.append((FIF.PENCIL_INK, "应用到可视化", self._page_dispatcher.make_activation_callback(kind, node_id)))
        elif kind in ("global_plot_style", "global_plot_theme"):
            manage_entries.append((FIF.PIE_SINGLE, "应用到可视化", self._page_dispatcher.make_activation_callback(kind, node_id)))
        elif kind == "global_group":
            if self._parse_extension_config_group_node_id(node_id) is not None:
                manage_entries.append((FIF.ADD, "新建配置", lambda: self._cmd_create_extension_config(node_id)))
        elif kind == "global_extension_config":
            manage_entries.append((getattr(FIF, "SETTING", FIF.DEVELOPER_TOOLS), "在数据管理页查看/编辑", self._page_dispatcher.make_activation_callback(kind, node_id)))
            manage_entries.append((FIF.COPY, "创建副本", lambda: self._cmd_duplicate_extension_config(node_id)))
            manage_entries.append((FIF.SAVE, "导出", lambda: self._cmd_export_extension_config(node_id)))
            if not bool(getattr(item, "is_default", False)):
                manage_entries.append((getattr(FIF, "PIN", FIF.SETTING), "设为默认", lambda: self._cmd_set_default_extension_config(node_id)))
        elif kind in ("global_ai_prompt", "global_ai_skill", "global_ai_agent"):
            manage_entries.append((FIF.EDIT, "在设置中查看", self._page_dispatcher.make_activation_callback(kind, node_id)))
        if self._can_edit_global_asset(kind, node_id):
            manage_entries.extend([
                (FIF.EDIT, "重命名", lambda: self._cmd_rename_global(kind, node_id, item.text(0))),
                (FIF.DELETE, "删除", lambda: self._cmd_delete_global(kind, node_id, item.text(0))),
            ])
        self._append_menu_section(menu, manage_entries)
        if menu.actions():
            self._append_tree_scope_actions(menu, separated=True)
            menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _build_node_menu(
        self,
        kind: str, node_id: str, item,
        import_entries: list,
        manage_entries: list,
    ) -> None:
        if kind == "folder":
            self._build_folder_menu(node_id, item, import_entries, manage_entries)
        elif kind == "data_file":
            self._build_data_file_menu(node_id, item, import_entries, manage_entries)
        elif kind == "source_file":
            self._build_source_file_menu(node_id, item, import_entries, manage_entries)
        elif kind == "series":
            self._build_series_menu(node_id, item, import_entries, manage_entries)
        elif kind == "image_work":
            self._build_image_work_menu(node_id, item, import_entries, manage_entries)
        elif kind == "picture":
            self._build_picture_menu(node_id, item, import_entries, manage_entries)
        elif kind == "curve":
            self._build_curve_menu(node_id, item, import_entries, manage_entries)
        elif kind == "pipeline":
            self._build_pipeline_menu(node_id, item, manage_entries)
        elif kind == "figure_template":
            self._build_figure_template_menu(node_id, item, manage_entries)
        elif kind == "report_template":
            self._build_report_template_menu(node_id, item, manage_entries)
        elif kind == "analysis_result":
            self._build_analysis_result_menu(node_id, item, import_entries, manage_entries)
        elif kind in ("ai_prompt", "ai_skill", "ai_agent", "ai_tool"):
            self._build_ai_menu(kind, node_id, item, manage_entries)

    def _build_folder_menu(self, node_id: str, item, import_entries: list, manage_entries: list) -> None:
        node = project_manager.get_node_by_id(node_id)
        is_protected = self._is_protected_folder(node)
        managed_group_type = self._folder_collection_group(node_id)
        if managed_group_type in self._MANAGED_FOLDER_GROUP_TYPES:
            if managed_group_type == "datasets":
                import_entries.append((self._NEW_DATASET_ACTION_ICON, "新建数据集", lambda: self._cmd_add_dataset_node(node_id)))
                import_entries.append((self._IMPORT_DATA_ACTION_ICON, "导入数据文件...", lambda: self._cmd_import_data_file(node_id)))
            if managed_group_type == "source_files":
                import_entries.append((FIF.DOWNLOAD, "批量导入源文件...", lambda: self._cmd_import_source_files(node_id)))
            if managed_group_type == "images":
                import_entries.append((FIF.PHOTO, "导入图片...", lambda: self._cmd_import_digitize_images(node_id)))
            import_entries.append((FIF.FOLDER_ADD, "新建子文件夹", lambda: self._cmd_add_child_folder(node_id)))
            if managed_group_type == "pictures":
                manage_entries.append((self._PICTURE_GROUP_ICON, "在文件夹打开", lambda: self._open_picture_folder(node_id)))
            elif managed_group_type == "source_files":
                manage_entries.append((self._SOURCE_FOLDER_ICON, "在文件夹打开", lambda: self._open_source_file_folder(node_id)))
        if not is_protected:
            manage_entries.extend([
                (FIF.EDIT, "重命名", lambda: self._rename_selected_item()),
                (FIF.DELETE, "删除", lambda: self._cmd_delete(node_id, item.text(0))),
            ])
            move_choices = self._move_target_choices("folder", node_id)
            if move_choices:
                manage_entries.append((FIF.SYNC, "移动到...", lambda: self._cmd_move_virtual("folder", node_id, move_choices)))
        if managed_group_type in self._MANAGED_FOLDER_GROUP_TYPES:
            manage_entries.append((FIF.SYNC, "清理空子文件夹", lambda: self._cmd_prune_empty_folders(node_id, scope_label=item.text(0))))

    def _build_data_file_menu(self, node_id: str, item, import_entries: list, manage_entries: list) -> None:
        move_choices = self._move_target_choices("data_file", node_id)
        manage_entries.extend([
            (FIF.PIE_SINGLE, "发送到可视化", self._page_dispatcher.make_activation_callback("data_file_to_chart", node_id)),
            (FIF.DEVELOPER_TOOLS, "发送到处理", self._page_dispatcher.make_activation_callback("data_file_to_process", node_id)),
            (FIF.SEARCH, "发送到分析", self._page_dispatcher.make_activation_callback("data_file_to_analysis", node_id)),
            (FIF.EDIT, "重命名", lambda: self._rename_selected_item()),
            (FIF.DELETE, "删除", lambda: self._cmd_delete(node_id, item.text(0))),
        ])
        if move_choices:
            manage_entries.append((FIF.SYNC, "移动到...", lambda: self._cmd_move_virtual("data_file", node_id, move_choices)))

    def _build_source_file_menu(self, node_id: str, item, import_entries: list, manage_entries: list) -> None:
        move_choices = self._move_target_choices("source_file", node_id)
        import_entries.extend([
            (self._IMPORT_DATA_ACTION_ICON, "导入到数据集", self._page_dispatcher.make_activation_callback("source_file_to_data", node_id)),
            (FIF.PHOTO, "导入到数字化", self._page_dispatcher.make_activation_callback("source_file_to_digitize", node_id)),
        ])
        manage_entries.extend([
            (self._SOURCE_FOLDER_ICON, "在文件夹打开", lambda: self._open_source_file_folder(node_id, source_node=True)),
            (FIF.EDIT, "重命名", lambda: self._rename_selected_item()),
            (FIF.DELETE, "删除", lambda: self._cmd_delete(node_id, item.text(0))),
        ])
        if move_choices:
            manage_entries.append((FIF.SYNC, "移动到...", lambda: self._cmd_move_virtual("source_file", node_id, move_choices)))

    def _build_series_menu(self, node_id: str, item, import_entries: list, manage_entries: list) -> None:
        move_choices = self._move_target_choices("series", node_id)
        manage_entries.extend([
            (FIF.PIE_SINGLE, "发送到可视化", self._page_dispatcher.make_activation_callback("series_to_chart", node_id)),
            (FIF.DEVELOPER_TOOLS, "发送到处理", self._page_dispatcher.make_activation_callback("series_to_process", node_id)),
            (FIF.SEARCH, "发送到分析", self._page_dispatcher.make_activation_callback("series_to_analysis", node_id)),
            (FIF.EDIT, "重命名", lambda: self._rename_selected_item()),
            (FIF.DELETE, "删除", lambda: self._cmd_delete_virtual("series", node_id, item.text(0))),
        ])
        if move_choices:
            manage_entries.append((FIF.SYNC, "移动到...", lambda: self._cmd_move_virtual("series", node_id, move_choices)))

    def _build_image_work_menu(self, node_id: str, item, import_entries: list, manage_entries: list) -> None:
        move_choices = self._move_target_choices("image_work", node_id)
        manage_entries.extend([
            (FIF.ADD, "新增曲线", self._page_dispatcher.make_activation_callback("image_work_add_curve", node_id)),
            (self._OPEN_DIGITIZE_ACTION_ICON, "打开取点", self._page_dispatcher.make_activation_callback("image_work", node_id)),
            (FIF.EDIT, "重命名", lambda: self._rename_selected_item()),
            (FIF.DELETE, "删除", lambda: self._cmd_delete(node_id, item.text(0))),
        ])
        if move_choices:
            manage_entries.append((FIF.SYNC, "移动到...", lambda: self._cmd_move_virtual("image_work", node_id, move_choices)))

    def _build_picture_menu(self, node_id: str, item, import_entries: list, manage_entries: list) -> None:
        move_choices = self._move_target_choices("picture", node_id)
        manage_entries.extend([
            (FIF.PIE_SINGLE, "发送到可视化", self._page_dispatcher.make_activation_callback("picture_to_chart", node_id)),
            (self._PICTURE_GROUP_ICON, "在文件夹打开", lambda: self._open_picture_folder(node_id, picture_node=True)),
            (FIF.EDIT, "重命名", lambda: self._rename_selected_item()),
            (FIF.DELETE, "删除", lambda: self._cmd_delete(node_id, item.text(0))),
        ])
        if move_choices:
            manage_entries.append((FIF.SYNC, "移动到...", lambda: self._cmd_move_virtual("picture", node_id, move_choices)))

    def _build_curve_menu(self, node_id: str, item, import_entries: list, manage_entries: list) -> None:
        move_choices = self._move_target_choices("curve", node_id)
        manage_entries.extend([
            (self._IMPORT_DATA_ACTION_ICON, "导出为数据列", self._page_dispatcher.make_activation_callback("curve_export_to_data_file", node_id)),
            (FIF.PIE_SINGLE, "发送到可视化", self._page_dispatcher.make_activation_callback("curve_to_chart", node_id)),
            (FIF.EDIT, "重命名", lambda: self._rename_selected_item()),
            (FIF.DELETE, "删除", lambda: self._cmd_delete_virtual("curve", node_id, item.text(0))),
        ])
        if move_choices:
            manage_entries.append((FIF.SYNC, "移动到...", lambda: self._cmd_move_virtual("curve", node_id, move_choices)))

    def _build_pipeline_menu(self, node_id: str, item, manage_entries: list) -> None:
        manage_entries.extend([
            (FIF.DEVELOPER_TOOLS, "加载到处理页", self._page_dispatcher.make_activation_callback("pipeline", node_id)),
            (FIF.EDIT, "重命名", lambda: self._rename_selected_item()),
            (FIF.DELETE, "删除", lambda: self._cmd_delete(node_id, item.text(0))),
        ])

    def _build_figure_template_menu(self, node_id: str, item, manage_entries: list) -> None:
        manage_entries.extend([
            (FIF.PIE_SINGLE, "加载到可视化", self._page_dispatcher.make_activation_callback("figure_template", node_id)),
            (FIF.EDIT, "重命名", lambda: self._rename_selected_item()),
            (FIF.DELETE, "删除", lambda: self._cmd_delete(node_id, item.text(0))),
        ])

    def _build_report_template_menu(self, node_id: str, item, manage_entries: list) -> None:
        manage_entries.extend([
            (FIF.SEARCH, "加载到分析页", self._page_dispatcher.make_activation_callback("report_template", node_id)),
            (FIF.EDIT, "重命名", lambda: self._rename_selected_item()),
            (FIF.DELETE, "删除", lambda: self._cmd_delete(node_id, item.text(0))),
        ])

    def _build_analysis_result_menu(self, node_id: str, item, import_entries: list, manage_entries: list) -> None:
        move_choices = self._move_target_choices("analysis_result", node_id)
        manage_entries.extend([
            (FIF.SEARCH, "发送到分析页", self._page_dispatcher.make_activation_callback("analysis_result", node_id)),
            (FIF.EDIT, "重命名", lambda: self._rename_selected_item()),
            (FIF.DELETE, "删除", lambda: self._cmd_delete(node_id, item.text(0))),
        ])
        if move_choices:
            manage_entries.append((FIF.SYNC, "移动到...", lambda: self._cmd_move_virtual("analysis_result", node_id, move_choices)))

    def _build_ai_menu(self, kind: str, node_id: str, item, manage_entries: list) -> None:
        manage_entries.extend([
            (FIF.EDIT, "编辑", self._page_dispatcher.make_activation_callback(kind, node_id)),
            (FIF.DELETE, "删除", lambda: self._cmd_delete(node_id, item.text(0))),
        ])
