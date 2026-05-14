"""
共享项目树组件 — ProjectTreeWidget

由 project_manager 数据驱动，可嵌入任意页面。
支持虚拟叶节点（DataSeries / Curve）、过滤模式、右键菜单、内联重命名。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QEvent, QItemSelectionModel, QPoint, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFontMetrics
from PySide6.QtWidgets import QAbstractItemView, QFileDialog, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (
    FluentIcon as FIF, InfoBar, InfoBarPosition, MessageBox, RoundMenu, ToolTip,
)
from core.global_assets import global_assets, make_plot_style_asset_key
from core.extension_api import build_extension_entry, extension_registry
from core.app_context import get_app_context
from core.ui_preferences import get_tree_name_display_mode
from app.project_tree_command_service import ProjectTreeCommandService
from ui.dialogs.project_close_dialog import ProjectCloseDecision, confirm_unsaved_project_close
from ui.dialogs.fluent_dialogs import SelectionDialog, TextInputDialog
from ui.widgets.project_tree_builder import ProjectTreeBuilder
from ui.widgets.project_tree_model import ProjectTreeItem
from ui.widgets.project_tree_page_dispatcher import ProjectTreePageDispatcher
from ui.widgets.project_tree_view import ProjectTreeView
from .project_tree_support import (
    _DATA_ICON,
    _DATASET_GROUP_ICON,
    _DIGITIZE_GROUP_ICON,
    _EXTENSION_CONFIG_GROUPS,
    _GROUP_ICON,
    _IMPORT_DATA_ACTION_ICON,
    _KIND_CONFIG,
    _MANAGED_FOLDER_GROUP_TYPES,
    _NEW_DATASET_ACTION_ICON,
    _OPEN_DIGITIZE_ACTION_ICON,
    _PROJECT_ICON,
    _PROJECT_ROLE,
    _ROOT_GROUP_LABELS,
    _ROOT_GROUP_ORDER,
    _ROOT_GROUP_TYPES,
    _ROLE,
    _SOURCE_FILE_ICON,
    _SOURCE_FOLDER_ICON,
    _SOURCE_IMAGE_SUFFIXES,
    _SYNTHETIC_GLOBAL_KINDS,
    _extension_config_name_key,
    add_menu_action,
    append_menu_section,
    _global_asset_sort_key,
    _series_color_icon,
    _sort_text_key,
    _wrap_text_height,
    is_protected_folder,
    is_root_group_folder,
)
from .project_tree_delegate import ProjectTreeWrapAnywhereDelegate
from .project_tree_drag_drop import ProjectTreeDragDropHelper
from .project_tree_menu_commands import ProjectTreeMenuBuilder


class _PMProxy:
    __slots__ = ()

    def __getattr__(self, name):
        pm = get_app_context().project_manager
        if pm is None:
            import core.project_manager as _pm_module
            pm = _pm_module.project_manager
        return getattr(pm, name)


project_manager = _PMProxy()


# 用于右键菜单图标引用
_PICTURE_GROUP_ICON = _SOURCE_FOLDER_ICON  # project_tree_support 中未导出, 本地引用


def _extension_config_sort_key(config) -> tuple[int, int, str, str]:
    name_key = _sort_text_key(getattr(config, "name", "") or getattr(config, "id", ""))
    return (0 if bool(getattr(config, "is_default", False)) else 1, name_key[0], name_key[1], name_key[2])


class ProjectTreeWidget(QWidget):
    """可嵌入任意页面的项目树组件。

    Signals:
        node_selected(kind, node_id)   — 单击节点
        node_activated(kind, node_id)  — 双击 / 回车
        project_modified()             — 树内操作导致数据变化
    """

    node_selected    = Signal(str, str)
    node_activated   = Signal(str, str)
    project_modified = Signal()
    refreshed = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._builder = ProjectTreeBuilder()
        self._projects = project_manager.projects
        self._filter_kinds: List[str] = []  # 空 = 显示全部
        self._focus_root_group_types: List[str] = []
        self._focus_global_group_keys: List[str] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tree = ProjectTreeView(self, self)
        self._tree.setHeaderHidden(True)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tree.setIndentation(14)
        self._tree.setWordWrap(True)
        self._tree.setTextElideMode(Qt.TextElideMode.ElideNone)
        self._tree.setUniformRowHeights(False)
        self._tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tree.header().setStretchLastSection(True)
        self._tree.viewport().setMouseTracking(True)
        self._tree.setDragEnabled(True)
        self._tree.setAcceptDrops(True)
        self._tree.viewport().setAcceptDrops(True)
        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self._tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._tree.setDropIndicatorShown(True)
        self._tree.setItemDelegate(ProjectTreeWrapAnywhereDelegate(self, self._tree))

        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemActivated.connect(self._on_item_activated)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._tree.viewport().installEventFilter(self)
        self._tree.itemExpanded.connect(self._on_item_expanded)

        layout.addWidget(self._tree)

        self._renaming = False
        self._item_cache: Dict[str, ProjectTreeItem] = {}
        self._ensuring_loaded: set[str] = set()
        self._branch_toggle_item_key: Optional[str] = None
        self._drag_source_item_key: Optional[str] = None
        self._drag_source_item_keys: List[str] = []
        self._focused_item_keys: List[str] = []
        self._focused_item_key: Optional[str] = None
        self._fluent_tooltip: Optional[ToolTip] = None
        self._name_display_mode = "elide"
        self._SYNTHETIC_GLOBAL_KINDS = _SYNTHETIC_GLOBAL_KINDS
        self._MANAGED_FOLDER_GROUP_TYPES = _MANAGED_FOLDER_GROUP_TYPES
        self._ROOT_GROUP_LABELS = _ROOT_GROUP_LABELS
        self._page_dispatcher = ProjectTreePageDispatcher(self.node_selected, self.node_activated)
        self._command_service = ProjectTreeCommandService(
            confirm_delete=self._confirm_tree_delete,
            confirm_batch_delete=self._confirm_tree_delete,
            choose_file=self._choose_tree_file,
            choose_files=self._choose_tree_files,
            prompt_text=self._prompt_tree_text,
            prompt_existing_text=self._prompt_tree_existing_text,
            choose_item=self._choose_tree_item,
            create_child_folder=self._create_child_folder,
            create_source_file_import_dialog=self._create_source_file_import_dialog,
            configure_source_file_import_target=self._lock_source_file_import_dialog_target,
            move_node_to_target=self._move_node_to_target,
            supports_data_file_import=self._supports_source_file_dataset_import,
            supports_digitize_import=self._supports_source_file_digitize_import,
            linked_tree_node_id=self._linked_tree_node_id,
            notify_warning=self._notify_tree_warning,
            notify_success=self._notify_tree_success,
            dialog_parent=self._dialog_parent,
            refresh=self.refresh,
            select_node=self.select_node,
            project_modified=self.project_modified.emit,
            last_error_message=project_manager.get_last_error_message,
        )

        # 初始化拖放辅助
        self._drag_drop_helper = ProjectTreeDragDropHelper(
            item_role_data=self._item_role_data,
            item_key=self._item_key,
            item_project_id=self._item_project_id,
            find_item_by_key=self._find_item_by_key,
            find_item=self._find_item,
            expand_item_ancestors=self._expand_item_ancestors,
            dialog_parent=self._dialog_parent,
            folder_collection_group=self._folder_collection_group,
            refresh=self.refresh,
            select_node=self.select_node,
            select_nodes=self._select_nodes,
            project_modified=self.project_modified.emit,
            command_service=self._command_service,
            _SOURCE_IMAGE_SUFFIXES=_SOURCE_IMAGE_SUFFIXES,
            _MANAGED_FOLDER_GROUP_TYPES=_MANAGED_FOLDER_GROUP_TYPES,
            _SYNTHETIC_GLOBAL_KINDS=_SYNTHETIC_GLOBAL_KINDS,
            _ROOT_GROUP_LABELS=_ROOT_GROUP_LABELS,
            _move_node_to_target=self._move_node_to_target,
            _batch_action_payloads=self._batch_action_payloads,
            _common_batch_move_choices=self._common_batch_move_choices,
            tree_view=self._tree,
        )

        # 初始化右键菜单构建器
        self._menu_builder = ProjectTreeMenuBuilder(
            tree_widget=self,
            add_menu_action=self._add_menu_action,
            append_menu_section=self._append_menu_section,
            append_tree_scope_actions=self._append_tree_scope_actions,
            batch_action_payloads=self._batch_action_payloads,
            common_batch_move_choices=self._common_batch_move_choices,
            command_service=self._command_service,
            page_dispatcher=self._page_dispatcher,
            dialog_parent=self._dialog_parent,
            refresh=self.refresh,
            select_node=self.select_node,
            project_modified=self.project_modified.emit,
            tree_view=self._tree,
            selected_items_for_context_menu=self._selected_items_for_context_menu,
            move_target_choices=self._move_target_choices,
            move_node_to_target=self._move_node_to_target,
            is_protected_folder=self._is_protected_folder,
            folder_collection_group=self._folder_collection_group,
            is_focus_active=self.is_focus_active,
            focus_selected_item=self.focus_selected_item,
            clear_focus=self.clear_focus,
            rename_selected_item=self.rename_selected_item,
            can_edit_global_asset=self._command_service.can_edit_global_asset,
            _extension_config_sort_key=_extension_config_sort_key,
            _parse_extension_config_group_node_id=self._parse_extension_config_group_node_id,
            _cmd_create_extension_config=self._cmd_create_extension_config,
            _cmd_duplicate_extension_config=self._cmd_duplicate_extension_config,
            _cmd_export_extension_config=self._cmd_export_extension_config,
            _cmd_set_default_extension_config=self._cmd_set_default_extension_config,
            _cmd_delete=self._cmd_delete,
            _cmd_delete_batch=self._cmd_delete_batch,
            _cmd_delete_virtual=self._cmd_delete_virtual,
            _cmd_delete_global=self._cmd_delete_global,
            _cmd_add_child_folder=self._cmd_add_child_folder,
            _cmd_add_dataset_node=self._cmd_add_dataset_node,
            _cmd_import_data_file=self._cmd_import_data_file,
            _cmd_import_source_files=self._cmd_import_source_files,
            _cmd_import_digitize_images=self._cmd_import_digitize_images,
            _cmd_rename_global=self._cmd_rename_global,
            _cmd_prune_empty_folders=self._cmd_prune_empty_folders,
            _cmd_move_batch=self._cmd_move_batch,
            _cmd_move_virtual=self._cmd_move_virtual,
            _open_picture_folder=self._open_picture_folder,
            _open_source_file_folder=self._open_source_file_folder,
            _SYNTHETIC_GLOBAL_KINDS=_SYNTHETIC_GLOBAL_KINDS,
            _MANAGED_FOLDER_GROUP_TYPES=_MANAGED_FOLDER_GROUP_TYPES,
            _PICTURE_GROUP_ICON=_PICTURE_GROUP_ICON,
            _SOURCE_FOLDER_ICON=_SOURCE_FOLDER_ICON,
            _NEW_DATASET_ACTION_ICON=_NEW_DATASET_ACTION_ICON,
            _IMPORT_DATA_ACTION_ICON=_IMPORT_DATA_ACTION_ICON,
            _OPEN_DIGITIZE_ACTION_ICON=_OPEN_DIGITIZE_ACTION_ICON,
            _PICTURE_GROUP_ICON_v2=_PICTURE_GROUP_ICON,
            save_current_project=self._save_current_project,
            save_current_project_as=self._save_current_project_as,
            close_current_project=self._close_current_project,
        )

        self.set_name_display_mode(get_tree_name_display_mode())

    # ─────────────────────────────────────────────────────────
    # 公开接口
    # ─────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """从 project_manager.projects 完整重建树。"""
        self._projects = project_manager.projects
        self._item_cache.clear()
        self._builder.build(self)

    def _save_current_project(self) -> bool:
        window = self.window()
        handler = getattr(window, "_save_current_project_from_panel", None)
        if callable(handler):
            return bool(handler())
        project = project_manager.current_project
        if project is None:
            return False
        file_path = project.file_path
        if not file_path:
            return self._save_current_project_as()
        try:
            project_manager.save(file_path)
        except Exception as exc:
            InfoBar.error("保存失败", str(exc), parent=self._dialog_parent(), position=InfoBarPosition.TOP)
            return False
        InfoBar.success("已保存", file_path, parent=self._dialog_parent(), position=InfoBarPosition.TOP)
        return True

    def _save_current_project_as(self) -> bool:
        window = self.window()
        handler = getattr(window, "_save_current_project_as_from_panel", None)
        if callable(handler):
            return bool(handler())
        project = project_manager.current_project
        if project is None:
            return False
        file_path, _ = QFileDialog.getSaveFileName(
            self._dialog_parent(),
            "另存项目",
            f"{project.name}.aline",
            "ALine 项目 (*.aline)",
        )
        if not file_path:
            return False
        try:
            project_manager.save(file_path)
        except Exception as exc:
            InfoBar.error("保存失败", str(exc), parent=self._dialog_parent(), position=InfoBarPosition.TOP)
            return False
        InfoBar.success("已另存", file_path, parent=self._dialog_parent(), position=InfoBarPosition.TOP)
        return True

    def _close_current_project(self) -> None:
        window = self.window()
        handler = getattr(window, "_close_current_project_from_panel", None)
        if callable(handler):
            handler()
            return
        project = project_manager.current_project
        if project is None:
            return
        if project.is_modified:
            decision = confirm_unsaved_project_close(project.name, self._dialog_parent())
            if decision == ProjectCloseDecision.CANCEL:
                return
            if decision == ProjectCloseDecision.SAVE and not self._save_current_project():
                return
        project_manager.close_current_project()
        self.refresh()

    def _schedule_wrapped_item_size_hint_update(self) -> None:
        QTimer.singleShot(0, self._update_wrapped_item_size_hints)

    def refreshed_emit(self) -> None:
        self.refreshed.emit()

    def expand_all_items(self) -> None:
        self._expand_all_items()

    def collapse_all_items(self) -> None:
        self._collapse_all_items()

    def all_expandable_items_expanded(self) -> bool:
        root = self._tree.invisibleRootItem()
        stack = [root.child(index) for index in range(root.childCount())]
        has_expandable_item = False
        while stack:
            item = stack.pop()
            if item is None or item.isHidden():
                continue
            if item.childCount() > 0:
                has_expandable_item = True
                if not item.isExpanded():
                    return False
                stack.extend(item.child(index) for index in range(item.childCount()))
        return has_expandable_item

    def select_node(self, node_id: str) -> None:
        """程序化选中节点（不触发 node_selected 信号）。"""
        self._ensure_node_loaded(node_id)
        item = self._find_item(node_id)
        if item:
            self._tree.blockSignals(True)
            self._tree.clearSelection()
            self._expand_item_ancestors(item)
            item.setSelected(True)
            self._tree.setCurrentItem(item)
            self._tree.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
            self._tree.blockSignals(False)

    def set_filter_kinds(
        self,
        kinds: List[str],
        *,
        focus_root_group_types: Optional[List[str]] = None,
        focus_global_group_keys: Optional[List[str]] = None,
    ) -> None:
        """只显示指定 kind 的节点（空列表 = 显示全部）。"""
        self._filter_kinds = list(kinds)
        self._focus_root_group_types = [
            canonical
            for canonical in (
                self._canonical_group_type(group_type)
                for group_type in list(focus_root_group_types or [])
            )
            if canonical
        ]
        self._focus_global_group_keys = [
            str(group_key or "").strip()
            for group_key in list(focus_global_group_keys or [])
            if str(group_key or "").strip()
        ]
        self.refresh()

    def set_name_display_mode(self, mode: str) -> None:
        self._name_display_mode = "elide" if mode == "elide" else "wrap"
        self._apply_name_display_mode()

    def is_focus_active(self) -> bool:
        return bool(self._focused_item_keys)

    def can_focus_selected_item(self) -> bool:
        return bool(self._selected_items_or_current())

    def focused_item_keys(self) -> List[str]:
        return list(self._focused_item_keys)

    def focus_item_keys(self, item_keys: List[str]) -> None:
        selected_keys = [str(item_key) for item_key in item_keys if item_key]
        if not selected_keys:
            return
        self._focused_item_keys = selected_keys
        self._focused_item_key = selected_keys[0]
        self._reapply_focus_view(preferred_selection_keys=selected_keys)

    def focus_selected_item(self) -> None:
        if not self.can_focus_selected_item():
            return
        selected_keys = self._selected_item_keys()
        if not selected_keys:
            return
        self.focus_item_keys(selected_keys)

    def clear_focus(self) -> None:
        if not self._focused_item_keys:
            return
        selected_keys = list(self._focused_item_keys)
        selected_key = self._current_item_key()
        self._focused_item_keys = []
        self._focused_item_key = None
        preferred_keys = selected_keys if selected_key is None else [selected_key, *[key for key in selected_keys if key != selected_key]]
        self._reapply_focus_view(preferred_selection_keys=preferred_keys)

    def get_selected_node(self) -> Optional[Tuple[str, str]]:
        """返回 (kind, node_id) 或 None。"""
        item = self._tree.currentItem()
        if item is None:
            return None
        d = item.data(0, _ROLE)
        if d:
            return d[0], d[1]
        return None

    def can_rename_selected_item(self) -> bool:
        items = self._selected_items_or_current()
        if len(items) != 1:
            return False
        item = items[0]
        self._activate_item_project(item)
        data = self._item_role_data(item)
        if not data:
            return False
        kind, node_id = data
        if kind == "project":
            return False
        if kind in _SYNTHETIC_GLOBAL_KINDS:
            return self._command_service.can_edit_global_asset(kind, node_id)
        if kind == "folder":
            return not self._is_protected_folder(project_manager.get_node_by_id(node_id))
        return True

    def can_delete_selected_items(self) -> bool:
        items = self._selected_items_or_current()
        if not items:
            return False
        payloads = self._batch_action_payloads(items)
        if payloads:
            return True
        if len(items) != 1:
            return False
        item = items[0]
        self._activate_item_project(item)
        data = self._item_role_data(item)
        if not data:
            return False
        kind, node_id = data
        if kind == "project":
            return False
        if kind in _SYNTHETIC_GLOBAL_KINDS:
            return self._command_service.can_edit_global_asset(kind, node_id)
        if kind == "folder":
            return not self._is_protected_folder(project_manager.get_node_by_id(node_id))
        return True

    def can_move_selected_items(self) -> bool:
        items = self._selected_items_or_current()
        if not items:
            return False
        payloads = self._batch_action_payloads(items)
        if payloads:
            return bool(self._common_batch_move_choices(payloads))
        if len(items) != 1:
            return False
        item = items[0]
        self._activate_item_project(item)
        data = self._item_role_data(item)
        if not data:
            return False
        kind, node_id = data
        return bool(self._move_target_choices(kind, node_id))

    def rename_selected_item(self) -> None:
        if not self.can_rename_selected_item():
            return
        item = self._selected_items_or_current()[0]
        self._activate_item_project(item)
        data = self._item_role_data(item)
        if not data:
            return
        kind, node_id = data
        current_name = item.text(0).strip()
        self._command_service.rename_selected_item(kind, node_id, current_name)

    def delete_selected_items(self) -> None:
        if not self.can_delete_selected_items():
            return
        items = self._selected_items_or_current()
        payloads = self._batch_action_payloads(items)
        if payloads:
            self._cmd_delete_batch(payloads)
            return
        item = items[0]
        self._activate_item_project(item)
        data = self._item_role_data(item)
        if not data:
            return
        kind, node_id = data
        if kind in _SYNTHETIC_GLOBAL_KINDS:
            self._cmd_delete_global(kind, node_id, item.text(0))
            return
        if kind in {"series", "curve"}:
            self._cmd_delete_virtual(kind, node_id, item.text(0))
            return
        self._cmd_delete(node_id, item.text(0))

    def move_selected_items(self) -> None:
        if not self.can_move_selected_items():
            return
        items = self._selected_items_or_current()
        payloads = self._batch_action_payloads(items)
        if payloads:
            choices = self._common_batch_move_choices(payloads)
            if choices:
                self._cmd_move_batch(payloads, choices)
            return
        item = items[0]
        self._activate_item_project(item)
        data = self._item_role_data(item)
        if not data:
            return
        kind, node_id = data
        choices = self._move_target_choices(kind, node_id)
        if choices:
            self._cmd_move_virtual(kind, node_id, choices)

    # ─────────────────────────────────────────────────────────
    # 树构建
    # ─────────────────────────────────────────────────────────

    def _build_children(
        self, project, parent_id: Optional[str], parent_item: Optional[ProjectTreeItem], *, depth: int = 1
    ) -> None:
        if project is None or project.tree is None or parent_item is None:
            return
        if parent_id is None:
            parent_data = parent_item.data(0, _ROLE)
            if parent_data and parent_data[0] == "project":
                depth = 2
        children = sorted(
            project.tree.get_children(parent_id),
            key=lambda node: self._tree_node_sort_key(node, parent_id),
        )
        for node in children:
            kind = node.kind
            if self._filter_kinds and kind not in self._filter_kinds:
                if kind != "folder":
                    continue
            item = self._get_or_create_item(node, project.id)
            if item.parent() != parent_item:
                parent_item.addChild(item)

            if depth > 1:
                self._build_children(project, node.id, item, depth=depth - 1)

                if kind == "data_file":
                    if not self._filter_kinds or "series" in self._filter_kinds or "data_file" in self._filter_kinds:
                        df = project.find_data_file(node.data_file_id)
                        if df:
                            for series in sorted(df.series, key=lambda item: _sort_text_key(item.name or item.id)):
                                child = self._make_virtual_series_item(series, project.id)
                                item.addChild(child)

                elif kind == "image_work":
                    if not self._filter_kinds or "curve" in self._filter_kinds or "image_work" in self._filter_kinds:
                        img = next((image for image in project.images if image.id == node.image_work_id), None)
                        if img:
                            for curve in sorted(img.curves, key=lambda item: _sort_text_key(item.name or item.id)):
                                child = self._make_virtual_curve_item(curve, project.id)
                                item.addChild(child)

                is_root_folder = kind == "folder" and parent_id is None and getattr(node, "group_type", None) in _ROOT_GROUP_TYPES
                is_protected_folder = self._is_protected_folder(node)
                show_empty_folder = not self._filter_kinds or "folder" in self._filter_kinds
                if kind == "folder" and not show_empty_folder and item.childCount() == 0 and not is_root_folder and not is_protected_folder:
                    parent_item.removeChild(item)
                    continue
            else:
                if self._node_has_visible_children(project, node):
                    self._build_placeholder_item(item)
                if self._filter_kinds and kind == "folder" and not self._node_has_visible_children(project, node):
                    is_root_folder = parent_id is None and getattr(node, "group_type", None) in _ROOT_GROUP_TYPES
                    is_protected = self._is_protected_folder(node)
                    if not is_root_folder and not is_protected:
                        parent_item.removeChild(item)
                        continue

    def _build_placeholder_item(self, parent_item: ProjectTreeItem) -> ProjectTreeItem:
        placeholder = self._tree.create_item("")
        parent_item.addChild(placeholder)
        return placeholder

    def _is_placeholder_item(self, item: Optional[ProjectTreeItem]) -> bool:
        if item is None:
            return False
        return item.data(0, _ROLE) is None

    def _node_has_visible_children(self, project, node) -> bool:
        kind = node.kind
        if kind == "folder":
            children = project.tree.get_children(node.id)
            if not children:
                return False
            if self._filter_kinds:
                return any(
                    child.kind in self._filter_kinds or child.kind == "folder"
                    for child in children
                )
            return True
        if kind == "data_file":
            df = project.find_data_file(getattr(node, "data_file_id", ""))
            if not df:
                return False
            if self._filter_kinds and "series" not in self._filter_kinds and "data_file" not in self._filter_kinds:
                return False
            return bool(df.series)
        if kind == "image_work":
            img = next((image for image in project.images if image.id == getattr(node, "image_work_id", "")), None)
            if not img:
                return False
            if self._filter_kinds and "curve" not in self._filter_kinds and "image_work" not in self._filter_kinds:
                return False
            return bool(img.curves)
        return False

    def _get_or_create_item(self, node, project_id: str) -> ProjectTreeItem:
        node_id = getattr(node, "id", None)
        if node_id and node_id in self._item_cache:
            item = self._item_cache[node_id]
            item.setData(0, _PROJECT_ROLE, project_id)
            return item
        item = self._make_item(node, project_id)
        if node_id:
            self._item_cache[node_id] = item
        return item

    def _on_item_expanded(self, item: ProjectTreeItem) -> None:
        self._lazy_load_children(item)

    def _lazy_load_children(self, item: Optional[ProjectTreeItem]) -> None:
        if item is None or item.childCount() != 1:
            return
        if not self._is_placeholder_item(item.child(0)):
            return
        placeholder = item.child(0)
        item.removeChild(placeholder)
        data = self._item_role_data(item)
        if not data:
            return
        kind, node_id = data
        project_id = self._item_project_id(item)
        project = next((p for p in self._projects if p.id == project_id), None)
        if project is None:
            return
        if kind == "project":
            self._build_children(project, None, item)
        elif kind == "data_file":
            self._build_virtual_children(project, "data_file", node_id, item)
        elif kind == "image_work":
            self._build_virtual_children(project, "image_work", node_id, item)
        elif kind == "folder" or kind in _ROOT_GROUP_TYPES:
            self._build_children(project, node_id, item)

    def _build_virtual_children(self, project, kind: str, node_id: str, parent_item: ProjectTreeItem) -> None:
        if kind == "data_file":
            node = project.tree.get_node(node_id)
            if node is None:
                return
            if not self._filter_kinds or "series" in self._filter_kinds or "data_file" in self._filter_kinds:
                df = project.find_data_file(getattr(node, "data_file_id", ""))
                if df:
                    for series in sorted(df.series, key=lambda item: _sort_text_key(item.name or item.id)):
                        child = self._make_virtual_series_item(series, project.id)
                        parent_item.addChild(child)
        elif kind == "image_work":
            node = project.tree.get_node(node_id)
            if node is None:
                return
            if not self._filter_kinds or "curve" in self._filter_kinds or "image_work" in self._filter_kinds:
                img = next((image for image in project.images if image.id == getattr(node, "image_work_id", "")), None)
                if img:
                    for curve in sorted(img.curves, key=lambda item: _sort_text_key(item.name or item.id)):
                        child = self._make_virtual_curve_item(curve, project.id)
                        parent_item.addChild(child)

    def _ensure_node_loaded(self, node_id: str) -> None:
        if node_id in self._ensuring_loaded:
            return
        self._ensuring_loaded.add(node_id)
        try:
            project = project_manager.current_project
            if project is None or project.tree is None:
                return
            current = project.tree.get_node(node_id)
            if current is None:
                for df in project.data_files:
                    if any(series.id == node_id for series in df.series):
                        for node in project.tree.nodes:
                            if getattr(node, "kind", None) == "data_file" and getattr(node, "data_file_id", None) == df.id:
                                current = node
                                break
                        break
                if current is None:
                    for img in project.images:
                        if any(curve.id == node_id for curve in img.curves):
                            for node in project.tree.nodes:
                                if getattr(node, "kind", None) == "image_work" and getattr(node, "image_work_id", None) == img.id:
                                    current = node
                                    break
                            break
            if current is None:
                return
            ancestor_ids: List[str] = []
            while current is not None:
                ancestor_ids.append(current.id)
                parent_id = getattr(current, "parent_id", None)
                current = project.tree.get_node(parent_id) if parent_id else None
            for ancestor_id in reversed(ancestor_ids):
                item = self._find_item(ancestor_id)
                if item is not None:
                    item.setExpanded(True)
                    self._lazy_load_children(item)
        finally:
            self._ensuring_loaded.discard(node_id)

    def _make_project_item(self, project) -> ProjectTreeItem:
        project_item = self._tree.create_item(project.name)
        project_item.setData(0, _ROLE, ("project", project.id))
        project_item.setData(0, _PROJECT_ROLE, project.id)
        project_item.setIcon(0, _PROJECT_ICON.icon())
        project_item.setToolTip(0, project.name)
        if project.id == project_manager.current_project_id:
            font = project_item.font(0)
            font.setBold(True)
            project_item.setFont(0, font)
        return project_item

    def _make_synthetic_item(self, label: str, kind: str, node_id: str, icon_fif) -> ProjectTreeItem:
        item = self._tree.create_item(label)
        item.setData(0, _ROLE, (kind, node_id))
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item.setIcon(0, icon_fif.icon())
        item.setToolTip(0, label)
        return item

    def _build_global_assets_root(self) -> None:
        focus_global_groups = set(self._focus_global_group_keys)
        focus_mode_active = bool(focus_global_groups)
        def _allowed(key: str) -> bool:
            return not focus_mode_active or key in focus_global_groups

        root = self._make_synthetic_item("全局资源", "global_root", "__global_root__", FIF.FOLDER)
        visible_children = 0
        if _allowed("pipelines"):
            pipelines = self._make_synthetic_item("Pipelines", "global_group", "__global_pipelines__", FIF.DEVELOPER_TOOLS)
            for item in sorted(global_assets.list_saved_pipelines(), key=lambda asset: _sort_text_key(asset.name or asset.id)):
                pipelines.addChild(self._make_synthetic_item(item.name, "global_pipeline", item.id, FIF.DEVELOPER_TOOLS))
            root.addChild(pipelines)
            visible_children += 1
        if _allowed("curve_styles"):
            curve_group = self._make_synthetic_item("曲线样式", "global_group", "__global_curve_styles__", FIF.PENCIL_INK)
            curve_templates = getattr(global_assets, "list_curve_style_templates", lambda include_builtin=True: [])(include_builtin=True)
            for tmpl in sorted(curve_templates, key=lambda t: (0 if bool(getattr(t, "is_builtin", False)) else 1, _sort_text_key(t.name))):
                curve_group.addChild(self._make_synthetic_item(tmpl.name, "global_curve_style_template", tmpl.id, FIF.PENCIL_INK))
            root.addChild(curve_group)
            visible_children += 1
        if _allowed("plot_styles"):
            plot_group = self._make_synthetic_item("绘图样式", "global_group", "__global_plot_styles__", FIF.PIE_SINGLE)
            plot_themes = sorted(global_assets.list_plot_themes(include_builtin=True), key=lambda t: (0 if bool(getattr(t, "is_builtin", False)) else 1, _sort_text_key(t.name)))
            for theme in plot_themes:
                plot_group.addChild(self._make_synthetic_item(theme.name, "global_plot_theme", make_plot_style_asset_key("theme", theme.id), FIF.PIE_SINGLE))
            templates = global_assets.list_figure_templates()
            for tmpl in sorted(
                templates,
                key=lambda t: (0 if bool(getattr(t, "is_builtin", False)) else 1, _sort_text_key(t.name)),
            ):
                plot_group.addChild(self._make_synthetic_item(tmpl.name, "global_plot_style", make_plot_style_asset_key("template", tmpl.id), FIF.PIE_SINGLE))
            root.addChild(plot_group)
            visible_children += 1
        if _allowed("report_templates"):
            report_group = self._make_synthetic_item("报告模板", "global_group", "__global_report_templates__", FIF.DOCUMENT)
            for tmpl in sorted(
                global_assets.list_report_templates(include_builtin=True),
                key=lambda t: (0 if bool(getattr(t, "is_builtin", False)) else 1, _sort_text_key(t.name)),
            ):
                report_group.addChild(self._make_synthetic_item(tmpl.name, "global_report_template", tmpl.id, FIF.DOCUMENT))
            root.addChild(report_group)
            visible_children += 1
        ext_group = None
        allowed_categories = {key.split(":", 1)[1] for key in focus_global_groups if key.startswith("extension_configs:")}
        if not focus_mode_active or allowed_categories:
            ext_group = self._make_synthetic_item("扩展配置", "global_group", "__global_extension_configs__", getattr(FIF, "SETTING", FIF.DEVELOPER_TOOLS))
            for category, label, icon in _EXTENSION_CONFIG_GROUPS:
                group_key = f"extension_configs:{category}"
                if not _allowed(group_key):
                    continue
                items = self._build_extension_config_group_items(category)
                group_item = self._make_synthetic_item(label, "global_group", f"extension_config_group|{category}", icon)
                if items:
                    for item in items:
                        group_item.addChild(item)
                else:
                    group_item.addChild(self._make_synthetic_item("空分组", "global_group", f"extension_config_group|{category}|empty", getattr(FIF, "INFO", FIF.DOCUMENT)))
                ext_group.addChild(group_item)
                visible_children += 1
            if ext_group.childCount() > 0:
                root.addChild(ext_group)
        if visible_children > 0:
            self._tree.addTopLevelItem(root)

    def _build_extension_config_group_items(self, category: str) -> List[ProjectTreeItem]:
        extension_map = self._extension_registry_name_map(category)
        configs_by_type: dict[str, list[Any]] = {}
        for config in global_assets.list_extension_configs(category=category):
            type_id = str(getattr(config, "extension_type", "") or "").strip()
            if not type_id:
                continue
            configs_by_type.setdefault(type_id, []).append(config)

        ordered_types = sorted(extension_map, key=lambda value: (extension_map.get(value, value).lower(), value))

        items: List[ProjectTreeItem] = []
        for type_id in ordered_types:
            configs = sorted(configs_by_type.get(type_id, []), key=_extension_config_sort_key)
            extension_label = extension_map.get(type_id) or (str(getattr(configs[0], "extension_name", "") or "").strip() if configs else "")
            items.append(self._build_extension_config_extension_item(category, type_id, extension_label, configs))
        return items

    @staticmethod
    def _extension_registry_name_map(category: str) -> dict[str, str]:
        if category == "plot":
            extensions = extension_registry.list_plot()
        elif category == "processing":
            extensions = extension_registry.list_processing()
        elif category == "digitize":
            extensions = extension_registry.list_digitize()
        else:
            extensions = extension_registry.list_analysis()
        name_map: dict[str, str] = {}
        for extension in extensions:
            entry = build_extension_entry(extension)
            type_id = str(entry.get("type") or "").strip()
            if not type_id:
                continue
            if not entry.get("listed", True) or not entry.get("settings"):
                continue
            name_map[type_id] = str(entry.get("name") or type_id)
        return name_map

    def _build_extension_config_extension_item(
        self,
        category: str,
        extension_type: str,
        extension_label: Optional[str],
        configs: List[Any],
    ) -> ProjectTreeItem:
        label = str(extension_label or extension_type or "扩展").strip() or "扩展"
        item = self._make_synthetic_item(
            label,
            "global_group",
            f"__global_extension_configs__:{category}:{extension_type}",
            getattr(FIF, "SETTING", FIF.DEVELOPER_TOOLS),
        )
        entry = self._extension_entry_for_category_type(category, extension_type)
        if entry is not None:
            description = str(entry.get("description") or "").strip()
            if description:
                item.setToolTip(0, description)
        for config in configs:
            item.addChild(
                self._make_synthetic_item(
                    config.name,
                    "global_extension_config",
                    config.id,
                    getattr(FIF, "SETTING", FIF.DEVELOPER_TOOLS),
                )
            )
        return item

    def _make_item(self, node, project_id: str) -> ProjectTreeItem:
        kind = node.kind
        icon, _ = _KIND_CONFIG.get(kind, (FIF.FOLDER, None))
        if kind == "folder":
            icon_qicon = self._folder_icon(node, getattr(node, "group_type", None)).icon()
        elif kind == "source_file":
            icon_qicon = self._source_file_icon(node).icon()
        else:
            icon_qicon = icon.icon()
        item = self._tree.create_item(getattr(node, "name", "") or getattr(node, "id", ""))
        item.setData(0, _ROLE, (kind, node.id))
        item.setData(0, _PROJECT_ROLE, project_id)
        item.setIcon(0, icon_qicon)
        tooltip = getattr(node, "name", "") or getattr(node, "id", "")
        item.setToolTip(0, str(tooltip))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
        self._item_cache[node.id] = item
        return item

    def _make_virtual_series_item(self, series, project_id: str) -> ProjectTreeItem:
        item = self._tree.create_item(series.name or series.id)
        item.setData(0, _ROLE, ("series", series.id))
        item.setData(0, _PROJECT_ROLE, project_id)
        color = series.color or "#0078D4"
        item.setIcon(0, _series_color_icon(color))
        item.setToolTip(0, series.name or series.id)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
        return item

    def _make_virtual_curve_item(self, curve, project_id: str) -> ProjectTreeItem:
        item = self._tree.create_item(curve.name or curve.id)
        item.setData(0, _ROLE, ("curve", curve.id))
        item.setData(0, _PROJECT_ROLE, project_id)
        color = curve.color or "#0078D4"
        item.setIcon(0, _series_color_icon(color))
        item.setToolTip(0, curve.name or curve.id)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
        return item

    def _tree_node_sort_key(self, node, parent_id: Optional[str]) -> tuple[int, int, str, str]:
        if parent_id is None:
            group_type = getattr(node, "group_type", None)
            order = _ROOT_GROUP_ORDER.get(str(group_type) if group_type else "", 99)
            name_key = _sort_text_key(getattr(node, "name", "") or getattr(node, "id", ""))
            return (order, name_key[0], name_key[1], name_key[2])
        name_key = _sort_text_key(getattr(node, "name", "") or getattr(node, "id", ""))
        return (0, name_key[0], name_key[1], name_key[2])

    # ─────────────────────────────────────────────────────────
    # 事件处理
    # ─────────────────────────────────────────────────────────

    def _activate_item_project(self, item: Optional[ProjectTreeItem]) -> None:
        if item is None:
            return
        project_id = self._item_project_id(item)
        if project_id:
            self._activate_project_id(project_id)

    def _activate_project_id(self, project_id: Optional[str]) -> None:
        if not project_id:
            return
        previous_project_id = project_manager.current_project_id
        project_manager.set_current_project(project_id)
        if project_id != previous_project_id:
            window = self.window()
            update_window_title = getattr(window, "_update_window_title", None)
            if callable(update_window_title):
                update_window_title()

    def _on_item_clicked(self, item: ProjectTreeItem, _col: int) -> None:
        if self._renaming:
            return
        if self._consume_branch_toggle_click(item):
            item.setExpanded(not item.isExpanded())
            return
        self._activate_item_project(item)
        data = self._item_role_data(item)
        if data:
            self.node_selected.emit(data[0], data[1])

    def _on_item_activated(self, item: ProjectTreeItem, _col: int) -> None:
        self._activate_item_project(item)
        data = self._item_role_data(item)
        if data:
            self.node_activated.emit(data[0], data[1])

    def eventFilter(self, watched, event):
        if watched == self._tree.viewport():
            if event.type() == QEvent.Type.ToolTip:
                self._show_fluent_tooltip_for_event(event)
                return True
            if event.type() == QEvent.Type.MouseButtonPress:
                self._hide_fluent_tooltip()
                item = self._tree.itemAt(event.pos())
                if event.button() == Qt.MouseButton.LeftButton:
                    branch_key = self._project_branch_toggle_key(item, event.pos().x())
                    if branch_key is not None:
                        if item is not None:
                            item.setExpanded(not item.isExpanded())
                            if item.isExpanded():
                                self._lazy_load_children(item)
                        return True
                if event.button() == Qt.MouseButton.LeftButton and self._tree.itemAt(event.pos()) is None:
                    self._clear_drag_source_item()
                    return False
            if event.type() == QEvent.Type.DragEnter:
                self._remember_drag_source_item(self._tree.itemAt(event.pos()))
                return False
            if event.type() == QEvent.Type.DragLeave:
                if self._drag_source_item_key:
                    self._clear_drag_source_item()
                return False
        return super().eventFilter(watched, event)

    def _on_item_changed(self, item: ProjectTreeItem, _col: int) -> None:
        if not self._renaming:
            return
        self._renaming = False
        self._activate_item_project(item)
        data = self._item_role_data(item)
        if not data:
            return
        kind, node_id = data
        current_name = item.text(0).strip()
        if not current_name:
            return
        if kind in _SYNTHETIC_GLOBAL_KINDS:
            self._command_service.rename_global_asset(kind, node_id, current_name)
        else:
            self._command_service.rename_node_by_kind(kind, node_id, current_name)
        self._schedule_wrapped_item_size_hint_update()
        self.project_modified.emit()

    # ─────────────────────────────────────────────────────────
    # 右键菜单（委托给 ProjectTreeMenuBuilder）
    # ─────────────────────────────────────────────────────────

    def _on_context_menu(self, pos) -> None:
        self._menu_builder.build_context_menu(pos)

    # ─────────────────────────────────────────────────────────
    # 命令（提供给菜单构建器的回调）
    # ─────────────────────────────────────────────────────────

    def _cmd_delete(self, node_id: str, node_name: str) -> None:
        self._command_service.delete_node(node_id, node_name)

    def _cmd_add_child_folder(self, parent_id: str) -> None:
        self._command_service.add_child_folder(parent_id)

    def _cmd_add_dataset_node(self, parent_id: str) -> None:
        self._command_service.add_dataset_node(parent_id)

    def _confirm_tree_delete(self, title: str, message: str) -> bool:
        w = MessageBox(title, message, self._dialog_parent())
        return w.exec()

    def _prompt_tree_text(self, title: str, label: str, placeholder: str) -> tuple[str, bool]:
        return TextInputDialog.get_text(self._dialog_parent(), title, label, placeholder=placeholder)

    def _prompt_tree_existing_text(self, title: str, label: str, text: str) -> tuple[str, bool]:
        return TextInputDialog.get_text(self._dialog_parent(), title, label, text=text)

    def _notify_tree_warning(self, title: str, content: str) -> None:
        InfoBar.warning(title, content, parent=self._dialog_parent(), position=InfoBarPosition.TOP, duration=3000)

    def _notify_tree_success(self, title: str, content: str) -> None:
        InfoBar.success(title, content, parent=self._dialog_parent(), position=InfoBarPosition.TOP, duration=3000)

    def _choose_tree_item(self, title: str, label: str, items: list[str]) -> tuple[str, bool]:
        return SelectionDialog.get_item(self._dialog_parent(), title, label, items)

    def _choose_tree_files(self, title: str, file_filter: str) -> list[str]:
        paths, _ = QFileDialog.getOpenFileNames(self._dialog_parent(), title, "", file_filter)
        return paths

    def _choose_tree_file(self, title: str, file_filter: str) -> str:
        path, _ = QFileDialog.getOpenFileName(self._dialog_parent(), title, "", file_filter)
        return path

    def _cmd_import_data_file(self, parent_id: Optional[str] = None) -> None:
        self._command_service.import_data_file(parent_id)

    def _cmd_import_source_files(self, parent_id: Optional[str] = None) -> None:
        self._command_service.import_source_files(parent_id)

    def _cmd_import_digitize_images(self, parent_id: Optional[str] = None) -> None:
        self._command_service.import_digitize_images(parent_id)

    def _cmd_rename_virtual(self, kind: str, node_id: str, current_name: str) -> None:
        self._command_service.rename_virtual(kind, node_id, current_name)

    def _cmd_prune_empty_folders(
        self,
        root_id: Optional[str] = None,
        *,
        scope_label: str = "项目树",
        project_id: Optional[str] = None,
    ) -> None:
        resolved_project_id = self._resolve_scope_project_id(root_id=root_id, project_id=project_id)
        if resolved_project_id:
            self._activate_project_id(resolved_project_id)
        self._command_service.prune_empty_folders(root_id, scope_label=scope_label)
        if root_id is None and self.is_focus_active():
            self.clear_focus()

    def _cmd_delete_batch(self, payloads: List[Dict[str, object]]) -> None:
        self._command_service.delete_batch(payloads)

    def _cmd_move_batch(self, payloads: List[Dict[str, object]], choices: List[Tuple[str, str]]) -> None:
        self._command_service.move_batch(payloads, choices)

    def _cmd_delete_virtual(self, kind: str, node_id: str, node_name: str) -> None:
        self._command_service.delete_virtual(kind, node_id, node_name)

    def _cmd_rename_global(self, kind: str, node_id: str, current_name: str) -> None:
        self._command_service.rename_global(kind, node_id, current_name)

    def _cmd_delete_global(self, kind: str, node_id: str, node_name: str) -> None:
        self._command_service.delete_global(kind, node_id, node_name)

    def _move_target_choices(self, kind: str, node_id: str) -> List[Tuple[str, str]]:
        p = project_manager.current_project
        if p is None:
            return []
        choices: List[Tuple[str, str]] = []
        if kind == "series":
            current_parent_id = None
            for df in p.data_files:
                if any(series.id == node_id for series in df.series):
                    current_parent_id = df.id
                    break
            for df in p.data_files:
                if df.id != current_parent_id:
                    choices.append((df.name, df.id))
        elif kind == "curve":
            current_parent_id = None
            for img in p.images:
                if any(curve.id == node_id for curve in img.curves):
                    current_parent_id = img.id
                    break
            for img in p.images:
                if img.id != current_parent_id:
                    choices.append((img.name, img.id))
        elif kind == "folder" and p.tree is not None:
            node = p.tree.get_node(node_id)
            if node is None:
                return []
            required_group = self._folder_collection_group(node_id)
            if required_group is None:
                return []

            def _is_descendant(candidate_id: str) -> bool:
                current = p.tree.get_node(candidate_id)
                while current is not None and getattr(current, "kind", None) == "folder":
                    parent_id = getattr(current, "parent_id", None)
                    if parent_id == node.id:
                        return True
                    current = p.tree.get_node(parent_id) if parent_id else None
                return False

            for folder in p.tree.nodes:
                if folder.kind != "folder" or folder.id == node.id:
                    continue
                if self._folder_collection_group(folder.id) != required_group:
                    continue
                if _is_descendant(folder.id):
                    continue
                choices.append((self._folder_path_label(folder.id), folder.id))
            choices.sort(key=lambda item: item[0])
        elif kind in {"data_file", "source_file", "image_work", "picture", "analysis_result", "pipeline", "figure_template", "report_template", "ai_prompt", "ai_skill", "ai_agent", "ai_tool"} and p.tree is not None:
            node = p.tree.get_node(node_id)
            if node is None or getattr(node, "parent_id", None) is None:
                return []
            required_group = self._folder_collection_group(getattr(node, "parent_id", None))
            if required_group is None:
                return []
            for folder in p.tree.nodes:
                if folder.kind != "folder":
                    continue
                if folder.id == node.parent_id:
                    continue
                if self._folder_collection_group(folder.id) != required_group:
                    continue
                choices.append((self._folder_path_label(folder.id), folder.id))
            choices.sort(key=lambda item: item[0])
        return choices

    def _move_node_to_target(self, kind: str, node_id: str, target_id: str) -> bool:
        if kind == "series":
            return project_manager.move_series_to_data_file(node_id, target_id)
        if kind == "curve":
            return project_manager.move_curve_to_image(node_id, target_id)
        p = project_manager.current_project
        if p is None or p.tree is None:
            return False
        order = p.tree.get_siblings_max_order(target_id) + 1
        return project_manager.move_node(node_id, target_id, order)

    def _cmd_move_virtual(self, kind: str, node_id: str, choices: List[Tuple[str, str]]) -> None:
        self._command_service.move_virtual(kind, node_id, choices)

    def _selected_items_for_context_menu(self, anchor_item: ProjectTreeItem) -> List[ProjectTreeItem]:
        selected_items = [item for item in self._tree.selectedItems() if item is not None]
        if anchor_item not in selected_items:
            anchor_project_id = self._item_project_id(anchor_item)
            selected_project_ids = {self._item_project_id(item) for item in selected_items}
            if not selected_items or len(selected_project_ids) != 1 or anchor_project_id not in selected_project_ids:
                self._tree.clearSelection()
                anchor_item.setSelected(True)
                selected_items = [anchor_item]
        self._tree.setCurrentItem(anchor_item)
        return selected_items

    def _batch_action_payloads(self, items: List[ProjectTreeItem]) -> List[Dict[str, object]]:
        if len(items) < 2:
            return []
        payloads: List[Dict[str, object]] = []
        expected_kind: Optional[str] = None
        expected_project_id: Optional[str] = None
        for item in items:
            data = self._item_role_data(item)
            if not data:
                return []
            kind, node_id = data
            if kind in {"project", "global_root", "global_group"} or kind in self._SYNTHETIC_GLOBAL_KINDS:
                return []
            node = project_manager.get_node_by_id(node_id)
            if kind == "folder" and self._is_protected_folder(node):
                return []
            if expected_kind is None:
                expected_kind = kind
                expected_project_id = self._item_project_id(item)
            elif kind != expected_kind or self._item_project_id(item) != expected_project_id:
                return []
            payloads.append({"kind": kind, "node_id": node_id, "name": item.text(0).strip()})
        return payloads

    def _common_batch_move_choices(self, payloads: List[Dict[str, object]]) -> List[Tuple[str, str]]:
        common_map: Optional[Dict[str, str]] = None
        for payload in payloads:
            current_map = {
                choice_id: label
                for label, choice_id in self._move_target_choices(str(payload["kind"]), str(payload["node_id"]))
            }
            if common_map is None:
                common_map = current_map
                continue
            common_map = {
                choice_id: common_map.get(choice_id, label)
                for choice_id, label in current_map.items()
                if choice_id in common_map
            }
        if not common_map:
            return []
        return sorted(((label, choice_id) for choice_id, label in common_map.items()), key=lambda item: item[0])

    # ─────────────────────────────────────────────────────────
    # 树节点查找与查询
    # ─────────────────────────────────────────────────────────

    def _find_item(self, node_id: str) -> Optional[ProjectTreeItem]:
        self._ensure_node_loaded(node_id)
        def _search(parent: Optional[ProjectTreeItem]) -> Optional[ProjectTreeItem]:
            count = self._tree.topLevelItemCount() if parent is None else parent.childCount()
            for index in range(count):
                item = self._tree.topLevelItem(index) if parent is None else parent.child(index)
                d = item.data(0, _ROLE)
                if d and d[1] == node_id:
                    return item
                found = _search(item)
                if found is not None:
                    return found
            return None
        return _search(None)

    def _selected_items_or_current(self) -> List[ProjectTreeItem]:
        items = list(self._tree.selectedItems())
        if items:
            return items
        current = self._tree.currentItem()
        return [current] if current is not None else []

    def _resolve_scope_project_id(
        self,
        *,
        root_id: Optional[str] = None,
        project_id: Optional[str] = None,
        items: Optional[List[ProjectTreeItem]] = None,
    ) -> Optional[str]:
        if project_id and project_manager.get_project(project_id) is not None:
            return project_id
        if root_id:
            root_item = self._find_item(root_id)
            if root_item is not None:
                root_project_id = self._item_project_id(root_item)
                if root_project_id:
                    return root_project_id
        source_items = list(items or self._selected_items_or_current())
        project_ids = {self._item_project_id(item) for item in source_items if self._item_project_id(item)}
        if len(project_ids) == 1:
            return next(iter(project_ids))
        current_project_id = self._item_project_id(self._tree.currentItem())
        if current_project_id:
            return current_project_id
        if len(self._projects) == 1:
            return self._projects[0].id
        return project_manager.current_project_id

    def _selected_item_keys(self, items: Optional[List[ProjectTreeItem]] = None) -> List[str]:
        source_items = self._selected_items_or_current() if items is None else items
        keys: List[str] = []
        for item in source_items:
            key = self._item_key(item)
            if key and key not in keys:
                keys.append(key)
        return keys

    def _item_key(self, item: Optional[ProjectTreeItem]) -> Optional[str]:
        if item is None:
            return None
        d = item.data(0, _ROLE)
        if d:
            return d[1]
        return None

    def _item_role_data(self, item: Optional[ProjectTreeItem]) -> Optional[Tuple[str, str]]:
        if item is None:
            return None
        d = item.data(0, _ROLE)
        if d:
            return d[0], d[1]
        return None

    def _item_project_id(self, item: Optional[ProjectTreeItem]) -> Optional[str]:
        if item is None:
            return None
        project_id = item.data(0, _PROJECT_ROLE)
        if project_id:
            return project_id
        parent = item.parent()
        if parent is not None:
            return self._item_project_id(parent)
        return None

    def _is_protected_folder(self, node) -> bool:
        return is_protected_folder(node)

    def _dialog_parent(self) -> QWidget:
        window = self.window()
        return window if isinstance(window, QWidget) else self

    def _folder_icon(self, node, group_type: Optional[str]):
        from qfluentwidgets import FluentIcon as FIF
        if is_root_group_folder(node):
            group_icon = _GROUP_ICON.get(str(group_type) if group_type else "")
            if group_icon is not None:
                return group_icon
        return FIF.FOLDER

    def _source_file_icon(self, node):
        from qfluentwidgets import FluentIcon as FIF
        if node is None:
            return FIF.DOCUMENT
        path = project_manager.get_source_file_path(getattr(node, "source_file_id", ""))
        if path and Path(path).suffix.lower() in _SOURCE_IMAGE_SUFFIXES:
            return FIF.PHOTO
        return _SOURCE_FILE_ICON

    def _tooltip_item_at_event(self, event) -> Optional[ProjectTreeItem]:
        if hasattr(event, "position"):
            return self._tree.itemAt(event.position().toPoint())
        if hasattr(event, "pos"):
            return self._tree.itemAt(event.pos())
        return None

    def _tooltip_global_pos(self, event) -> QPoint:
        viewport = self._tree.viewport()
        if hasattr(event, "globalPos"):
            return event.globalPos()
        if hasattr(event, "position"):
            return viewport.mapToGlobal(event.position().toPoint())
        if hasattr(event, "pos"):
            return viewport.mapToGlobal(event.pos())
        return viewport.mapToGlobal(viewport.rect().center())

    def _show_fluent_tooltip_for_event(self, event) -> None:
        item = self._tooltip_item_at_event(event)
        text = ""
        if item is not None:
            try:
                text = item.toolTip(0).strip()
            except RuntimeError:
                text = ""
        if not text:
            self._hide_fluent_tooltip()
            return
        if self._fluent_tooltip is None:
            self._fluent_tooltip = ToolTip(text, self._dialog_parent())
        self._fluent_tooltip.setText(text)
        self._fluent_tooltip.adjustSize()
        self._fluent_tooltip.move(self._tooltip_global_pos(event) + QPoint(12, 18))
        self._fluent_tooltip.show()

    def _hide_fluent_tooltip(self) -> None:
        if self._fluent_tooltip is not None:
            self._fluent_tooltip.hide()

    # ─────────────────────────────────────────────────────────
    # 树作用域操作
    # ─────────────────────────────────────────────────────────

    def _append_tree_scope_actions(
        self,
        menu: RoundMenu,
        separated: bool = False,
        *,
        focus_items: Optional[List[ProjectTreeItem]] = None,
        project_id: Optional[str] = None,
    ) -> None:
        if separated and menu.actions():
            menu.addSeparator()
        focus_items = list(self._selected_items_or_current() if focus_items is None else focus_items)
        focus_keys = set(self.focused_item_keys())
        selected_key_list = self._selected_item_keys(focus_items)
        selected_keys = set(selected_key_list)
        if focus_keys and (not selected_keys or selected_keys == focus_keys):
            self._add_menu_action(menu, getattr(FIF, "CANCEL", FIF.CLOSE), "退出专注", self.clear_focus)
        else:
            if focus_items:
                if len(focus_items) > 1:
                    label = "切换专注到所选" if self.is_focus_active() else "专注所选"
                else:
                    label = "切换专注到此处" if self.is_focus_active() else "专注此处"
                self._add_menu_action(
                    menu,
                    getattr(FIF, "PIN", getattr(FIF, "VIEW", FIF.SEARCH)),
                    label,
                    lambda _checked=False, keys=list(selected_key_list): self.focus_item_keys(keys),
                )
            if self.is_focus_active():
                self._add_menu_action(menu, getattr(FIF, "CANCEL", FIF.CLOSE), "退出专注", self.clear_focus)
        self._add_menu_action(
            menu,
            FIF.SYNC,
            "清理空文件夹",
            lambda _checked=False, target_project_id=project_id: self._cmd_prune_empty_folders(project_id=target_project_id),
        )

    def _expand_all_items(self) -> None:
        def _walk(item: Optional[ProjectTreeItem]) -> None:
            if item is None or item.isHidden():
                return
            self._lazy_load_children(item)
            if item.childCount() > 0:
                item.setExpanded(True)
            index = 0
            while index < item.childCount():
                _walk(item.child(index))
                index += 1
        for index in range(self._tree.topLevelItemCount()):
            _walk(self._tree.topLevelItem(index))

    def _collapse_all_items(self) -> None:
        def _walk(item: Optional[ProjectTreeItem]) -> None:
            if item is None or item.isHidden():
                return
            if item.childCount() > 0:
                item.setExpanded(False)
            for index in range(item.childCount()):
                _walk(item.child(index))
        for index in range(self._tree.topLevelItemCount()):
            _walk(self._tree.topLevelItem(index))

    def _add_menu_action(self, menu: RoundMenu, icon, text: str, callback):
        return add_menu_action(menu, icon, text, callback)

    def _append_menu_section(self, menu: RoundMenu, entries: List[Tuple[object, str, object]]) -> None:
        visible_entries = [entry for entry in entries if entry is not None]
        if not visible_entries:
            return
        append_menu_section(menu, visible_entries)

    # ─────────────────────────────────────────────────────────
    # 导入对话框/文件支持
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _supports_source_file_dataset_import(file_path: str) -> bool:
        from ui.dialogs.import_dialog import SUPPORTED_IMPORT_SUFFIXES
        return Path(file_path).suffix.lower() in set(SUPPORTED_IMPORT_SUFFIXES)

    @staticmethod
    def _supports_source_file_digitize_import(file_path: str) -> bool:
        return Path(file_path).suffix.lower() in _SOURCE_IMAGE_SUFFIXES

    def _create_source_file_import_dialog(self, file_path: str):
        from ui.dialogs.import_dialog import ImportDialog
        dialog = ImportDialog(self._dialog_parent())
        dialog.load_file(file_path)
        return dialog

    def _lock_source_file_import_dialog_target(self, dialog, target_data_file_id: Optional[str] = None) -> None:
        combo = getattr(dialog, "_data_file_target_combo", None)
        raw_keys = getattr(dialog, "_data_file_target_keys", None)
        if combo is None or not isinstance(raw_keys, (list, tuple)):
            return
        keys = list(raw_keys)
        if not keys:
            return
        target_index = 0
        if target_data_file_id:
            try:
                target_index = keys.index(target_data_file_id)
            except ValueError:
                target_index = 0
        combo.setCurrentIndex(target_index)
        combo.setEnabled(False)

    def _linked_tree_node_id(self, kind: str, attr_name: str, attr_value: str) -> Optional[str]:
        project = project_manager.current_project
        if project is None or project.tree is None:
            return None
        for node in project.tree.nodes:
            if getattr(node, "kind", None) != kind:
                continue
            if getattr(node, attr_name, None) == attr_value:
                return node.id
        return None

    # ─────────────────────────────────────────────────────────
    # 拖放操作（委托给 ProjectTreeDragDropHelper）
    # ─────────────────────────────────────────────────────────

    def _normalized_source_file_drop_target(self, target_item: Optional[ProjectTreeItem]) -> Tuple[Optional[str], Optional[str]]:
        return self._drag_drop_helper.normalized_source_file_drop_target(target_item)

    def _perform_source_file_drop_action(self, source_id: str, target_item: Optional[ProjectTreeItem], *, defer_view_refresh: bool = False) -> bool:
        return self._drag_drop_helper.perform_source_file_drop_action(source_id, target_item, defer_view_refresh=defer_view_refresh)

    def _open_picture_folder(self, node_id: Optional[str], *, picture_node: bool = False) -> None:
        target_path = ""
        if picture_node and node_id:
            node = project_manager.get_node_by_id(node_id)
            if node is not None and getattr(node, "kind", None) == "picture":
                picture_id = getattr(node, "picture_id", "")
                picture_path = project_manager.get_picture_path(picture_id) if picture_id else ""
                if picture_path:
                    target_path = str(Path(picture_path).parent)
        else:
            target_path = project_manager.resolve_picture_folder_path(node_id, create=True)
        if not target_path:
            InfoBar.warning("提示", "当前节点没有可打开的图片文件夹", parent=self, position=InfoBarPosition.TOP)
            return
        folder_path = Path(target_path)
        folder_path.mkdir(parents=True, exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder_path))):
            InfoBar.error("打开失败", str(folder_path), parent=self, position=InfoBarPosition.TOP)

    def _open_source_file_folder(self, node_id: Optional[str], *, source_node: bool = False) -> None:
        target_path = ""
        if source_node and node_id:
            node = project_manager.get_node_by_id(node_id)
            if node is not None and getattr(node, "kind", None) == "source_file":
                source_path = project_manager.get_source_file_path(getattr(node, "source_file_id", ""))
                if source_path:
                    target_path = str(Path(source_path).parent)
        else:
            target_path = project_manager.resolve_source_file_folder_path(node_id, create=True)
        if not target_path:
            InfoBar.warning("提示", "当前节点没有可打开的源文件夹", parent=self, position=InfoBarPosition.TOP)
            return
        folder_path = Path(target_path)
        folder_path.mkdir(parents=True, exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder_path))):
            InfoBar.error("打开失败", str(folder_path), parent=self, position=InfoBarPosition.TOP)

    @staticmethod
    def _canonical_group_type(group_type: Optional[str]) -> Optional[str]:
        if group_type in {"dataset_set", "datasets"}:
            return "datasets"
        if group_type in {"source_files"}:
            return "source_files"
        if group_type in {"image_set", "images"}:
            return "images"
        if group_type in {"picture_set", "pictures"}:
            return "pictures"
        return group_type

    def _folder_collection_group(self, node_id: Optional[str]) -> Optional[str]:
        current = project_manager.get_node_by_id(node_id) if node_id else None
        while current is not None and getattr(current, "kind", None) == "folder":
            group_type = self._canonical_group_type(getattr(current, "group_type", None))
            if group_type in _MANAGED_FOLDER_GROUP_TYPES:
                return group_type
            parent_id = getattr(current, "parent_id", None)
            current = project_manager.get_node_by_id(parent_id) if parent_id else None
        return None

    def _create_child_folder(self, parent_id: str, name: str):
        clean_name = name.strip()
        if not clean_name:
            return None
        group_type = self._folder_collection_group(parent_id)
        if group_type not in _MANAGED_FOLDER_GROUP_TYPES:
            return None
        return project_manager.add_folder(clean_name, parent_id=parent_id, group_type=group_type)

    def _resolve_drop_target_id(self, source_kind: str, source_id: str, target_item: Optional[ProjectTreeItem]) -> Optional[str]:
        return self._drag_drop_helper.resolve_drop_target_id(source_kind, source_id, target_item)

    def _resolve_virtual_drop_container_id(self, target_kind: str, target_id: str) -> Optional[str]:
        return self._drag_drop_helper._resolve_virtual_drop_container_id(target_kind, target_id)

    def _perform_drop_move(self, source_item: Optional[ProjectTreeItem], target_item: Optional[ProjectTreeItem], defer_view_refresh: bool = False) -> bool:
        return self._drag_drop_helper.perform_drop_move(source_item, target_item, defer_view_refresh=defer_view_refresh)

    def _perform_batch_drop_move(self, source_items: List[ProjectTreeItem], target_item: Optional[ProjectTreeItem], defer_view_refresh: bool = False) -> bool:
        return self._drag_drop_helper.perform_batch_drop_move(source_items, target_item, defer_view_refresh=defer_view_refresh)

    def _finalize_drop_move(self, source_id: str) -> None:
        self._drag_drop_helper._finalize_drop_move(source_id)

    def _finalize_batch_drop_move(self, source_ids: List[str]) -> None:
        self._drag_drop_helper._finalize_batch_drop_move(source_ids)

    def _remember_drag_source_item(self, item: Optional[ProjectTreeItem]) -> None:
        self._drag_drop_helper.remember_drag_source_item(item)

    def _remember_drag_source_items(self, items: List[ProjectTreeItem]) -> None:
        self._drag_drop_helper.remember_drag_source_items(items)

    def _drag_source_item_for_drop(self, fallback_item: Optional[ProjectTreeItem]) -> Optional[ProjectTreeItem]:
        return self._drag_drop_helper.drag_source_item_for_drop(fallback_item)

    def _drag_source_items_for_drop(self, fallback_item: Optional[ProjectTreeItem]) -> List[ProjectTreeItem]:
        return self._drag_drop_helper.drag_source_items_for_drop(fallback_item)

    def _clear_drag_source_item(self) -> None:
        self._drag_drop_helper.clear_drag_source_item()

    # ─────────────────────────────────────────────────────────
    # 节点选择与展开管理
    # ─────────────────────────────────────────────────────────

    def _select_nodes(self, node_ids: List[str]) -> None:
        self._apply_selection_nodes(node_ids, block_signals=True)

    def _apply_selection_nodes(self, node_ids: List[str], *, block_signals: bool) -> None:
        clean_ids = [str(node_id) for node_id in node_ids if node_id]
        if not clean_ids:
            return
        if block_signals:
            self._tree.blockSignals(True)
        try:
            self._tree.clearSelection()
            current_item = None
            for node_id in clean_ids:
                self._ensure_node_loaded(node_id)
                item = self._find_item(node_id)
                if item is None:
                    continue
                self._expand_item_ancestors(item)
                item.setSelected(True)
                current_item = item
            if current_item is not None:
                self._tree.setCurrentItem(current_item, 0, QItemSelectionModel.SelectionFlag.NoUpdate)
        finally:
            if block_signals:
                self._tree.blockSignals(False)

    def _folder_path_label(self, folder_id: str) -> str:
        label = project_manager.format_tree_path_label(folder_id, separator="/", omit_root_group=True)
        if label and label != folder_id:
            return label
        folder = project_manager.get_node_by_id(folder_id)
        group_type = getattr(folder, "group_type", None) if folder is not None else None
        fallback = _ROOT_GROUP_LABELS.get(str(group_type or ""), "")
        if fallback:
            return fallback
        if folder is not None:
            name = str(getattr(folder, "name", "") or "").strip()
            if name:
                return name
        return folder_id

    def _current_item_key(self) -> Optional[str]:
        return self._item_key(self._tree.currentItem())

    def _capture_expansion_state(self) -> Dict[str, bool]:
        state: Dict[str, bool] = {}
        def _walk(item: Optional[ProjectTreeItem]) -> None:
            if item is None:
                return
            key = self._item_key(item)
            if key is not None:
                state[key] = item.isExpanded()
            for index in range(item.childCount()):
                _walk(item.child(index))
        for index in range(self._tree.topLevelItemCount()):
            _walk(self._tree.topLevelItem(index))
        return state

    def _restore_expansion_state(self, state: Dict[str, bool]) -> None:
        if not state:
            return
        def _walk(item: Optional[ProjectTreeItem]) -> None:
            if item is None:
                return
            key = self._item_key(item)
            if key in state:
                item.setExpanded(state[key])
                if state[key]:
                    self._lazy_load_children(item)
            for index in range(item.childCount()):
                _walk(item.child(index))
        for index in range(self._tree.topLevelItemCount()):
            _walk(self._tree.topLevelItem(index))

    def _find_item_by_key(self, item_key: Optional[str]) -> Optional[ProjectTreeItem]:
        if not item_key:
            return None
        self._ensure_node_loaded(item_key)
        def _search(parent: Optional[ProjectTreeItem]) -> Optional[ProjectTreeItem]:
            count = self._tree.topLevelItemCount() if parent is None else parent.childCount()
            for index in range(count):
                item = self._tree.topLevelItem(index) if parent is None else parent.child(index)
                if self._item_key(item) == item_key:
                    return item
                found = _search(item)
                if found is not None:
                    return found
            return None
        return _search(None)

    def _restore_selection(self, item_key: Optional[str]) -> None:
        if isinstance(item_key, list):
            keys = [key for key in item_key if key]
        elif item_key:
            keys = [item_key]
        else:
            keys = []
        if not keys:
            return

        current_item = None
        self._tree.clearSelection()
        for key in keys:
            self._ensure_node_loaded(key)
            item = self._find_item_by_key(key)
            if item is None:
                continue
            self._expand_item_ancestors(item)
            item.setSelected(True)
            current_item = item
        if current_item is not None:
            self._tree.setCurrentItem(current_item)

    def _reapply_focus_view(self, preferred_selection_keys: Optional[List[str]] = None) -> None:
        target_selection = list(preferred_selection_keys or [])
        self._tree.blockSignals(True)
        try:
            target_selection = self._apply_focus_view(target_selection)
            if target_selection:
                self._apply_selection_nodes(target_selection, block_signals=False)
        finally:
            self._tree.blockSignals(False)
        self._tree.viewport().update()
        self._tree.updateGeometry()

    def _apply_focus_view(self, preferred_selection_keys: Optional[List[str]] = None) -> List[str]:
        preferred_selection_keys = list(preferred_selection_keys or [])
        for key in list(self._focused_item_keys):
            self._ensure_node_loaded(key)
        focus_keys = [key for key in self._focused_item_keys if self._find_item_by_key(key) is not None]
        if focus_keys != self._focused_item_keys:
            self._focused_item_keys = focus_keys
            self._focused_item_key = focus_keys[0] if focus_keys else None
        focus_items = [self._find_item_by_key(key) for key in focus_keys]
        focus_items = [item for item in focus_items if item is not None]
        visible_keys = self._focus_visible_keys(focus_items) if focus_items else None
        def _walk(parent: Optional[ProjectTreeItem]) -> None:
            count = self._tree.topLevelItemCount() if parent is None else parent.childCount()
            for index in range(count):
                item = self._tree.topLevelItem(index) if parent is None else parent.child(index)
                if item is None:
                    continue
                item_key = self._item_key(item)
                item.setHidden(bool(visible_keys is not None and item_key not in visible_keys))
                _walk(item)
        _walk(None)
        if focus_items:
            for focus_item in focus_items:
                self._expand_item_ancestors(focus_item)
                if focus_item.childCount() > 0:
                    focus_item.setExpanded(True)
            if visible_keys:
                visible_selection = [key for key in preferred_selection_keys if key in visible_keys]
                if visible_selection:
                    return visible_selection
            return focus_keys[:1]
        for key in list(preferred_selection_keys):
            self._ensure_node_loaded(key)
        return [key for key in preferred_selection_keys if self._find_item_by_key(key) is not None]

    def _focus_visible_keys(self, focus_items: List[ProjectTreeItem]) -> set[str]:
        visible_keys: set[str] = set()
        if not focus_items:
            return visible_keys
        stack = list(focus_items)
        while stack:
            item = stack.pop()
            if item is None:
                continue
            current = item
            while current is not None:
                item_key = self._item_key(current)
                if item_key:
                    visible_keys.add(item_key)
                current = current.parent()
            child_stack = [item]
            while child_stack:
                current_item = child_stack.pop()
                item_key = self._item_key(current_item)
                if item_key:
                    visible_keys.add(item_key)
                child_stack.extend(current_item.child(index) for index in range(current_item.childCount()))
        return visible_keys

    def _expand_item_ancestors(self, item: Optional[ProjectTreeItem]) -> None:
        current = item
        while current is not None:
            current.setExpanded(True)
            self._lazy_load_children(current)
            current = current.parent()

    # ─────────────────────────────────────────────────────────
    # Size hint / 显示模式管理
    # ─────────────────────────────────────────────────────────

    def _update_wrapped_item_size_hints(self) -> None:
        viewport_width = max(180, self._tree.viewport().width())
        def _walk(item: Optional[ProjectTreeItem], depth: int) -> None:
            if item is None:
                return
            try:
                self._apply_wrapped_item_size_hint(item, viewport_width, depth)
                child_count = item.childCount()
            except RuntimeError:
                return
            for index in range(child_count):
                try:
                    child = item.child(index)
                except RuntimeError:
                    continue
                _walk(child, depth + 1)
        try:
            top_level_count = self._tree.topLevelItemCount()
        except RuntimeError:
            return
        for index in range(top_level_count):
            try:
                top_item = self._tree.topLevelItem(index)
            except RuntimeError:
                continue
            _walk(top_item, 0)

    def _update_wrapped_item_size_hint_for_item(self, item: Optional[ProjectTreeItem]) -> None:
        if item is None:
            return
        try:
            viewport_width = max(180, self._tree.viewport().width())
            self._apply_wrapped_item_size_hint(item, viewport_width, self._item_depth(item))
        except RuntimeError:
            return

    def _reset_item_size_hints(self) -> None:
        def _walk(item: Optional[ProjectTreeItem]) -> None:
            if item is None:
                return
            try:
                item.setSizeHint(0, QSize())
                child_count = item.childCount()
            except RuntimeError:
                return
            for index in range(child_count):
                try:
                    child = item.child(index)
                except RuntimeError:
                    continue
                _walk(child)
        try:
            top_level_count = self._tree.topLevelItemCount()
        except RuntimeError:
            return
        for index in range(top_level_count):
            try:
                top_item = self._tree.topLevelItem(index)
            except RuntimeError:
                continue
            _walk(top_item)

    def _apply_name_display_mode(self) -> None:
        wrap_mode = self._name_display_mode == "wrap"
        was_blocked = self._tree.signalsBlocked()
        if not was_blocked:
            self._tree.blockSignals(True)
        try:
            self._tree.setWordWrap(wrap_mode)
            self._tree.setTextElideMode(Qt.TextElideMode.ElideNone if wrap_mode else Qt.TextElideMode.ElideRight)
            self._tree.setUniformRowHeights(not wrap_mode)
            if wrap_mode:
                self._update_wrapped_item_size_hints()
            else:
                self._reset_item_size_hints()
            self._tree.viewport().update()
            self._tree.updateGeometry()
        finally:
            if not was_blocked:
                self._tree.blockSignals(False)

    @staticmethod
    def _item_depth(item: Optional[ProjectTreeItem]) -> int:
        depth = 0
        current = item.parent() if item is not None else None
        while current is not None:
            depth += 1
            current = current.parent()
        return depth

    def _apply_wrapped_item_size_hint(self, item: ProjectTreeItem, viewport_width: int, depth: int) -> None:
        try:
            text = item.text(0).strip()
            if not text:
                return
            font_metrics = QFontMetrics(item.font(0))
            indentation = max(0, depth) * max(12, self._tree.indentation())
            icon_size = self._tree.iconSize()
            icon_width = icon_size.width() if icon_size.isValid() else 16
            icon_height = icon_size.height() if icon_size.isValid() else 16
            available_width = max(120, viewport_width - indentation - icon_width - 44)
            text_height = _wrap_text_height(item.font(0), text, available_width)
            content_height = max(font_metrics.lineSpacing(), icon_height, text_height)
            item.setSizeHint(0, QSize(available_width, content_height + 10))
        except RuntimeError:
            return

    def _project_branch_toggle_key(self, item: Optional[ProjectTreeItem], x_pos: float) -> Optional[str]:
        data = self._item_role_data(item)
        if not data or data[0] != "project":
            return None
        try:
            if item is None:
                return None
            if item.childCount() == 0:
                return None
            rect = self._tree.visualItemRect(item)
        except RuntimeError:
            return None
        if not rect.isValid():
            return None
        if x_pos <= rect.left() + 20:
            return self._item_key(item)
        return None

    def _consume_branch_toggle_click(self, item: Optional[ProjectTreeItem]) -> bool:
        item_key = self._item_key(item)
        if item_key is not None and item_key == self._branch_toggle_item_key:
            self._branch_toggle_item_key = None
            return True
        return False

    # ─────────────────────────────────────────────────────────
    # Extension config group support
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _parse_extension_config_group_node_id(node_id: str) -> Optional[Tuple[str, str]]:
        parts = str(node_id or "").split(":")
        if len(parts) == 3 and parts[0] == "__global_extension_configs__":
            return (parts[1], parts[2])
        return None

    def _cmd_create_extension_config(self, group_node_id: str) -> None:
        parsed = self._parse_extension_config_group_node_id(group_node_id)
        if parsed is None:
            return
        category, extension_type = parsed
        entry = self._extension_entry_for_category_type(category, extension_type)
        base_name = self._extension_config_default_name(extension_type)
        extension_name = str(entry.get("name") if entry is not None else base_name).strip() or base_name
        extension_version = entry.get("version") if entry is not None else None
        name, ok = self._prompt_tree_existing_text("新建扩展配置", "名称:", base_name)
        if not ok:
            return
        from core.global_assets import global_assets
        try:
            config = global_assets.add_extension_config(
                category=category,
                extension_type=extension_type,
                extension_name=extension_name,
                extension_version=extension_version,
                name=name,
            )
        except ValueError:
            return
        config_id = config.id
        if config_id:
            self.refresh()

    def _cmd_duplicate_extension_config(self, config_id: str) -> None:
        from core.global_assets import global_assets
        config = global_assets.get_extension_config(config_id)
        if config is None:
            return
        duplicated = global_assets.add_extension_config(
            category=config.category,
            extension_type=config.extension_type,
            extension_name=config.extension_name,
            extension_version=config.extension_version,
            name=f"{config.name} 副本",
            options=dict(config.options or {}),
        )
        if duplicated:
            self.refresh()

    def _cmd_export_extension_config(self, config_id: str) -> None:
        from core.global_assets import global_assets
        config_payload = global_assets.export_extension_config_to_json(config_id)
        if config_payload is None:
            return
        default_name = f"{str(config_payload.get('name') or 'extension_config').strip()}.json"
        file_path, _ = QFileDialog.getSaveFileName(self, "导出扩展配置", default_name, "JSON (*.json)")
        if not file_path:
            return
        try:
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(config_payload, handle, ensure_ascii=False, indent=2)
        except Exception as exc:
            self._notify_tree_warning("导出失败", str(exc))
            return
        self._notify_tree_success("已导出", file_path)

    def _cmd_set_default_extension_config(self, config_id: str) -> None:
        from core.global_assets import global_assets
        if global_assets.set_extension_default_config(config_id) is None:
            return
        self.refresh()

    def _extension_config_default_name(self, extension_type: str) -> str:
        entry = self._extension_entry_for_category_type("", extension_type)
        if entry is not None:
            return str(entry.get("name") or extension_type).strip() or extension_type
        return extension_type

    @staticmethod
    def _extension_registry_extension_for_category_type(category: str, extension_type: str) -> Optional[Any]:
        type_id = str(extension_type or "").strip()
        if not type_id:
            return None
        category = str(category or "").strip()
        if category == "plot":
            return extension_registry.get_plot(type_id)
        if category == "processing":
            return extension_registry.get_processing(type_id)
        if category == "digitize":
            return extension_registry.get_digitize(type_id)
        if category == "analysis":
            return extension_registry.get_analysis(type_id)
        for getter in (
            extension_registry.get_processing,
            extension_registry.get_analysis,
            extension_registry.get_plot,
            extension_registry.get_digitize,
        ):
            entry = getter(type_id)
            if entry is not None:
                return entry
        return None

    def _extension_entry_for_category_type(self, category: str, extension_type: str) -> Optional[dict]:
        extension = self._extension_registry_extension_for_category_type(category, extension_type)
        if extension is None:
            return None
        return build_extension_entry(extension)

    def _next_extension_config_name(self, category: str, extension_type: str, base_name: str) -> str:
        from core.global_assets import global_assets
        existing_names = {
            cfg.name
            for cfg in global_assets.list_extension_configs()
            if cfg.extension_type == extension_type
        }
        name = base_name
        counter = 1
        while name in existing_names:
            counter += 1
            name = f"{base_name} ({counter})"
        return name
