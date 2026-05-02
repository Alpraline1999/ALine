"""
共享项目树组件 — ProjectTreeWidget

由 project_manager 数据驱动，可嵌入任意页面。
支持虚拟叶节点（DataSeries / Curve）、过滤模式、右键菜单、内联重命名。
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QEvent, QItemSelectionModel, QPoint, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFontMetrics
from PySide6.QtWidgets import QAbstractItemView, QFileDialog, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (
    FluentIcon as FIF, InfoBar, InfoBarPosition, RoundMenu, ToolTip,
)
from PySide6.QtWidgets import QTreeWidgetItem

from core.global_assets import global_assets, make_plot_style_asset_key
from core.extension_api import build_extension_entry, extension_registry
from core.project_manager import project_manager
from core.ui_preferences import get_tree_name_display_mode
from app.project_tree_command_service import ProjectTreeCommandService
from ui.dialogs.fluent_dialogs import SelectionDialog, TextInputDialog
from ui.widgets.project_tree_builder import ProjectTreeBuilder
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
    _PROTECTED_GROUP_TYPES,
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
)
from .project_tree_delegate import ProjectTreeWrapAnywhereDelegate
from .project_tree_drag_drop import ProjectTreeDragDropHelper
from .project_tree_menu_commands import ProjectTreeMenuBuilder


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

        layout.addWidget(self._tree)

        self._renaming = False  # 防止 itemChanged 循环
        self._branch_toggle_item_key: Optional[str] = None
        self._drag_source_item_key: Optional[str] = None
        self._drag_source_item_keys: List[str] = []
        self._focused_item_key: Optional[str] = None
        self._fluent_tooltip: Optional[ToolTip] = None
        self._name_display_mode = "elide"
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
        )

        self.set_name_display_mode(get_tree_name_display_mode())

    # ─────────────────────────────────────────────────────────
    # 公开接口
    # ─────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """从 project_manager.projects 完整重建树。"""
        self._projects = project_manager.projects
        self._builder.build(self)

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
        item = self._find_item(node_id)
        if item:
            self._tree.blockSignals(True)
            self._tree.clearSelection()
            self._expand_item_ancestors(item)
            item.setSelected(True)
            self._tree.setCurrentItem(item)
            self._tree.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
            self._tree.blockSignals(False)

    def set_filter_kinds(self, kinds: List[str], *, focus_root_group_types: Optional[List[str]] = None) -> None:
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
        self.refresh()

    def set_name_display_mode(self, mode: str) -> None:
        self._name_display_mode = "elide" if mode == "elide" else "wrap"
        self._apply_name_display_mode()

    def is_focus_active(self) -> bool:
        return bool(self._focused_item_key)

    def can_focus_selected_item(self) -> bool:
        return len(self._selected_items_or_current()) == 1

    def focus_selected_item(self) -> None:
        if not self.can_focus_selected_item():
            return
        item = self._selected_items_or_current()[0]
        item_key = self._item_key(item)
        if not item_key:
            return
        self._focused_item_key = item_key
        self._reapply_focus_view(preferred_selection_key=item_key)

    def clear_focus(self) -> None:
        if not self._focused_item_key:
            return
        selected_key = self._current_item_key()
        self._focused_item_key = None
        self._reapply_focus_view(preferred_selection_key=selected_key)

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
        self, project, parent_id: Optional[str], parent_item: Optional[QTreeWidgetItem]
    ) -> None:
        if project is None or project.tree is None or parent_item is None:
            return
        children = sorted(
            project.tree.get_children(parent_id),
            key=lambda node: self._tree_node_sort_key(node, parent_id),
        )
        for node in children:
            kind = node.kind
            if self._filter_kinds and kind not in self._filter_kinds:
                if kind != "folder":
                    continue
            item = self._make_item(node, project.id)
            parent_item.addChild(item)

            # 递归子节点
            self._build_children(project, node.id, item)

            # 为 DataFileNode 追加虚拟 DataSeries 叶节点
            if kind == "data_file":
                if not self._filter_kinds or "series" in self._filter_kinds or "data_file" in self._filter_kinds:
                    df = project.find_data_file(node.data_file_id)
                    if df:
                        for series in sorted(df.series, key=lambda item: _sort_text_key(item.name or item.id)):
                            child = self._make_virtual_series_item(series, project.id)
                            item.addChild(child)

            # 为 ImageWorkNode 追加虚拟 Curve 叶节点
            elif kind == "image_work":
                if not self._filter_kinds or "curve" in self._filter_kinds or "image_work" in self._filter_kinds:
                    img = next((image for image in project.images if image.id == node.image_work_id), None)
                    if img:
                        for curve in sorted(img.curves, key=lambda item: _sort_text_key(item.name or item.id)):
                            child = self._make_virtual_curve_item(curve, project.id)
                            item.addChild(child)

            # 过滤：文件夹下无可见子节点则隐藏（但受保护的系统文件夹始终保留）
            is_root_folder = kind == "folder" and parent_id is None and getattr(node, "group_type", None) in _ROOT_GROUP_TYPES
            is_protected_folder = self._is_protected_folder(node)
            show_empty_folder = not self._filter_kinds or "folder" in self._filter_kinds
            if kind == "folder" and not show_empty_folder and item.childCount() == 0 and not is_root_folder and not is_protected_folder:
                if parent_item is None:
                    idx = self._tree.indexOfTopLevelItem(item)
                    self._tree.takeTopLevelItem(idx)
                else:
                    parent_item.removeChild(item)
                continue

    def _make_project_item(self, project) -> QTreeWidgetItem:
        project_item = QTreeWidgetItem([project.name])
        project_item.setData(0, _ROLE, ("project", project.id))
        project_item.setData(0, _PROJECT_ROLE, project.id)
        project_item.setIcon(0, _PROJECT_ICON.icon())
        project_item.setToolTip(0, project.name)
        if project.id == project_manager.current_project_id:
            font = project_item.font(0)
            font.setBold(True)
            project_item.setFont(0, font)
        return project_item

    def _make_synthetic_item(self, label: str, kind: str, node_id: str, icon_fif) -> QTreeWidgetItem:
        item = QTreeWidgetItem([label])
        item.setData(0, _ROLE, (kind, node_id))
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item.setIcon(0, icon_fif.icon())
        item.setToolTip(0, label)
        return item

    def _build_global_assets_root(self) -> None:
        root = self._make_synthetic_item("全局资源", "global_root", "__global_root__", FIF.FOLDER)
        pipelines = self._make_synthetic_item("Pipelines", "global_group", "__global_pipelines__", FIF.DEVELOPER_TOOLS)
        for item in sorted(global_assets.list_saved_pipelines(), key=lambda asset: _sort_text_key(asset.name or asset.id)):
            pipelines.addChild(self._make_synthetic_item(item.name, "global_pipeline", item.id, FIF.DEVELOPER_TOOLS))
        root.addChild(pipelines)
        plot_group = self._make_synthetic_item("图表模板", "global_group", "__global_plot_style__", FIF.PIE_SINGLE)
        templates = global_assets.list_figure_templates()
        for tmpl in sorted(templates, key=lambda t: (0 if t.is_builtin else 1, _sort_text_key(t.name))):
            plot_group.addChild(self._make_synthetic_item(tmpl.name, "global_plot_style", make_plot_style_asset_key("template", tmpl.id), FIF.PIE_SINGLE))
        if hasattr(global_assets, "list_curve_style_templates"):
            for tmpl in sorted(global_assets.list_curve_style_templates(), key=lambda t: _sort_text_key(t.name)):
                plot_group.addChild(self._make_synthetic_item(tmpl.name, "global_curve_style_template", tmpl.id, FIF.PENCIL_INK))
        report_group = self._make_synthetic_item("报告模板", "global_group", "__global_report_templates__", FIF.DOCUMENT)
        for tmpl in sorted(global_assets.list_report_templates(), key=lambda t: _sort_text_key(t.name)):
            report_group.addChild(self._make_synthetic_item(tmpl.name, "global_report_template", tmpl.id, FIF.DOCUMENT))
        root.addChild(report_group)
        plot_configs = []
        for category, label, icon in _EXTENSION_CONFIG_GROUPS:
            items = self._build_extension_config_group_items(category)
            if items:
                group_item = self._make_synthetic_item(label, "global_group", f"extension_config_group|{category}", icon)
                for item in items:
                    group_item.addChild(item)
                plot_configs.append(group_item)
        if plot_configs:
            ext_group = self._make_synthetic_item("扩展配置", "global_group", "__global_extension_configs__", getattr(FIF, "SETTING", FIF.DEVELOPER_TOOLS))
            for item in plot_configs:
                ext_group.addChild(item)
            root.addChild(ext_group)
        # AI 配置组（Phase 9 已禁用收口，后续重做 AI 时再恢复）
        # 补回 plot_group
        root.insertChild(1, plot_group)
        self._tree.addTopLevelItem(root)

    def _build_extension_config_group_items(self, category: str) -> List[QTreeWidgetItem]:
        items: List[QTreeWidgetItem] = []
        for config in sorted(global_assets.list_extension_configs(category=category), key=_extension_config_sort_key):
            items.append(self._make_synthetic_item(config.name, "global_extension_config", config.id, getattr(FIF, "SETTING", FIF.DEVELOPER_TOOLS)))
        return items

    def _make_item(self, node, project_id: str) -> QTreeWidgetItem:
        kind = node.kind
        icon, _ = _KIND_CONFIG.get(kind, (FIF.FOLDER, None))
        if kind == "folder":
            icon_qicon = self._folder_icon(node, getattr(node, "group_type", None)).icon()
        elif kind == "source_file":
            icon_qicon = self._source_file_icon(node).icon()
        else:
            icon_qicon = icon.icon()
        item = QTreeWidgetItem([getattr(node, "name", "") or getattr(node, "id", "")])
        item.setData(0, _ROLE, (kind, node.id))
        item.setData(0, _PROJECT_ROLE, project_id)
        item.setIcon(0, icon_qicon)
        tooltip = getattr(node, "name", "") or getattr(node, "id", "")
        item.setToolTip(0, str(tooltip))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
        return item

    def _make_virtual_series_item(self, series, project_id: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([series.name or series.id])
        item.setData(0, _ROLE, ("series", series.id))
        item.setData(0, _PROJECT_ROLE, project_id)
        color = series.color or "#0078D4"
        item.setIcon(0, _series_color_icon(color))
        item.setToolTip(0, series.name or series.id)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
        return item

    def _make_virtual_curve_item(self, curve, project_id: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([curve.name or curve.id])
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

    def _activate_item_project(self, item: Optional[QTreeWidgetItem]) -> None:
        if item is None:
            return
        project_id = self._item_project_id(item)
        if project_id:
            project_manager.set_current_project(project_id)

    def _on_item_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        if self._renaming:
            return
        if self._consume_branch_toggle_click(item):
            item.setExpanded(not item.isExpanded())
            return
        self._activate_item_project(item)
        data = self._item_role_data(item)
        if data:
            self.node_selected.emit(data[0], data[1])

    def _on_item_activated(self, item: QTreeWidgetItem, _col: int) -> None:
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

    def _on_item_changed(self, item: QTreeWidgetItem, _col: int) -> None:
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
        dlg = TextInputDialog(title, label, placeholder, parent=self._dialog_parent())
        ok = dlg.exec()
        return dlg.lineEdit.text().strip(), ok

    def _prompt_tree_existing_text(self, title: str, label: str, text: str) -> tuple[str, bool]:
        dlg = TextInputDialog(title, label, text, parent=self._dialog_parent())
        ok = dlg.exec()
        return dlg.lineEdit.text().strip(), ok

    def _notify_tree_warning(self, title: str, content: str) -> None:
        InfoBar.warning(title, content, parent=self._dialog_parent(), position=InfoBarPosition.TOP, duration=3000)

    def _notify_tree_success(self, title: str, content: str) -> None:
        InfoBar.success(title, content, parent=self._dialog_parent(), position=InfoBarPosition.TOP, duration=3000)

    def _choose_tree_item(self, title: str, label: str, items: list[str]) -> tuple[str, bool]:
        dlg = SelectionDialog(title, label, items, parent=self._dialog_parent())
        ok = dlg.exec()
        return dlg.get_selected_item(), ok

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

    def _cmd_prune_empty_folders(self, root_id: Optional[str] = None, *, scope_label: str = "项目树") -> None:
        self._command_service.prune_empty_folders(root_id, scope_label=scope_label)

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
        elif kind in {"data_file", "source_file", "image_work", "picture", "analysis_result"} and p.tree is not None:
            node = p.tree.get_node(node_id)
            if node is None:
                return []
            required_group = {
                "data_file": "datasets",
                "source_file": "source_files",
                "image_work": "images",
                "picture": "pictures",
                "analysis_result": "analysis_result_group",
            }[kind]
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

    def _selected_items_for_context_menu(self, anchor_item: QTreeWidgetItem) -> List[QTreeWidgetItem]:
        selected_items = [item for item in self._tree.selectedItems() if item is not None]
        if anchor_item not in selected_items:
            self._tree.clearSelection()
            anchor_item.setSelected(True)
            selected_items = [anchor_item]
        self._tree.setCurrentItem(anchor_item)
        return selected_items

    def _batch_action_payloads(self, items: List[QTreeWidgetItem]) -> List[Dict[str, object]]:
        if len(items) < 2:
            return []
        selected_keys = {self._item_key(item) for item in items}
        payloads: List[Dict[str, object]] = []
        expected_kind: Optional[str] = None
        expected_project_id: Optional[str] = None
        for item in items:
            data = self._item_role_data(item)
            if not data:
                return []
            kind, node_id = data
            if kind not in {"series", "curve"}:
                return []
            if expected_kind is None:
                expected_kind = kind
                expected_project_id = self._item_project_id(item)
            elif kind != expected_kind or self._item_project_id(item) != expected_project_id:
                return []
            payloads.append({"kind": kind, "node_id": node_id, "name": item.text(0).strip()})
        return payloads

    def _common_batch_move_choices(self, payloads: List[Dict[str, object]]) -> List[Tuple[str, str]]:
        seen_ids: set[str] = set()
        choices: List[Tuple[str, str]] = []
        for payload in payloads:
            for label, choice_id in self._move_target_choices(str(payload["kind"]), str(payload["node_id"])):
                if choice_id not in seen_ids:
                    seen_ids.add(choice_id)
                    choices.append((label, choice_id))
        return choices

    # ─────────────────────────────────────────────────────────
    # 树节点查找与查询
    # ─────────────────────────────────────────────────────────

    def _find_item(self, node_id: str) -> Optional[QTreeWidgetItem]:
        def _search(parent: Optional[QTreeWidgetItem]) -> Optional[QTreeWidgetItem]:
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

    def _selected_items_or_current(self) -> List[QTreeWidgetItem]:
        items = list(self._tree.selectedItems())
        if items:
            return items
        current = self._tree.currentItem()
        return [current] if current is not None else []

    def _item_key(self, item: Optional[QTreeWidgetItem]) -> Optional[str]:
        if item is None:
            return None
        d = item.data(0, _ROLE)
        if d:
            return d[1]
        return None

    def _item_role_data(self, item: Optional[QTreeWidgetItem]) -> Optional[Tuple[str, str]]:
        if item is None:
            return None
        d = item.data(0, _ROLE)
        if d:
            return d[0], d[1]
        return None

    def _item_project_id(self, item: Optional[QTreeWidgetItem]) -> Optional[str]:
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
        if node is None:
            return False
        group_type = getattr(node, "group_type", None)
        return group_type in _PROTECTED_GROUP_TYPES

    def _dialog_parent(self) -> QWidget:
        window = self.window()
        return window if isinstance(window, QWidget) else self

    def _folder_icon(self, node, group_type: Optional[str]):
        from qfluentwidgets import FluentIcon as FIF
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

    def _tooltip_item_at_event(self, event) -> Optional[QTreeWidgetItem]:
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

    def _append_tree_scope_actions(self, menu: RoundMenu, separated: bool = False) -> None:
        if separated and menu.actions():
            menu.addSeparator()
        focus_items = self._selected_items_or_current()
        focus_item = focus_items[0] if len(focus_items) == 1 else None
        focus_key = self._item_key(focus_item)
        if focus_key and focus_key == self._focused_item_key:
            self._add_menu_action(menu, getattr(FIF, "CANCEL", FIF.CLOSE), "退出专注", self.clear_focus)
        else:
            if focus_item is not None:
                label = "切换专注到此处" if self.is_focus_active() else "专注此处"
                self._add_menu_action(menu, getattr(FIF, "PIN", getattr(FIF, "VIEW", FIF.SEARCH)), label, self.focus_selected_item)
            if self.is_focus_active():
                self._add_menu_action(menu, getattr(FIF, "CANCEL", FIF.CLOSE), "退出专注", self.clear_focus)
        self._add_menu_action(menu, FIF.SYNC, "清理空文件夹", self._cmd_prune_empty_folders)

    def _expand_all_items(self) -> None:
        def _walk(item: Optional[QTreeWidgetItem]) -> None:
            if item is None or item.isHidden():
                return
            if item.childCount() > 0:
                item.setExpanded(True)
            for index in range(item.childCount()):
                _walk(item.child(index))
        for index in range(self._tree.topLevelItemCount()):
            _walk(self._tree.topLevelItem(index))

    def _collapse_all_items(self) -> None:
        def _walk(item: Optional[QTreeWidgetItem]) -> None:
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

    def _normalized_source_file_drop_target(self, target_item: Optional[QTreeWidgetItem]) -> Tuple[Optional[str], Optional[str]]:
        return self._drag_drop_helper.normalized_source_file_drop_target(target_item)

    def _perform_source_file_drop_action(self, source_id: str, target_item: Optional[QTreeWidgetItem], *, defer_view_refresh: bool = False) -> bool:
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

    def _resolve_drop_target_id(self, source_kind: str, source_id: str, target_item: Optional[QTreeWidgetItem]) -> Optional[str]:
        return self._drag_drop_helper.resolve_drop_target_id(source_kind, source_id, target_item)

    def _resolve_virtual_drop_container_id(self, target_kind: str, target_id: str) -> Optional[str]:
        return self._drag_drop_helper._resolve_virtual_drop_container_id(target_kind, target_id)

    def _perform_drop_move(self, source_item: Optional[QTreeWidgetItem], target_item: Optional[QTreeWidgetItem], defer_view_refresh: bool = False) -> bool:
        return self._drag_drop_helper.perform_drop_move(source_item, target_item, defer_view_refresh=defer_view_refresh)

    def _perform_batch_drop_move(self, source_items: List[QTreeWidgetItem], target_item: Optional[QTreeWidgetItem], defer_view_refresh: bool = False) -> bool:
        return self._drag_drop_helper.perform_batch_drop_move(source_items, target_item, defer_view_refresh=defer_view_refresh)

    def _finalize_drop_move(self, source_id: str) -> None:
        self._drag_drop_helper._finalize_drop_move(source_id)

    def _finalize_batch_drop_move(self, source_ids: List[str]) -> None:
        self._drag_drop_helper._finalize_batch_drop_move(source_ids)

    def _remember_drag_source_item(self, item: Optional[QTreeWidgetItem]) -> None:
        self._drag_drop_helper.remember_drag_source_item(item)

    def _remember_drag_source_items(self, items: List[QTreeWidgetItem]) -> None:
        self._drag_drop_helper.remember_drag_source_items(items)

    def _drag_source_item_for_drop(self, fallback_item: Optional[QTreeWidgetItem]) -> Optional[QTreeWidgetItem]:
        return self._drag_drop_helper.drag_source_item_for_drop(fallback_item)

    def _drag_source_items_for_drop(self, fallback_item: Optional[QTreeWidgetItem]) -> List[QTreeWidgetItem]:
        return self._drag_drop_helper.drag_source_items_for_drop(fallback_item)

    def _clear_drag_source_item(self) -> None:
        self._drag_drop_helper.clear_drag_source_item()

    # ─────────────────────────────────────────────────────────
    # 节点选择与展开管理
    # ─────────────────────────────────────────────────────────

    def _select_nodes(self, node_ids: List[str]) -> None:
        clean_ids = [str(node_id) for node_id in node_ids if node_id]
        if not clean_ids:
            return
        self._tree.blockSignals(True)
        try:
            self._tree.clearSelection()
            current_item = None
            for node_id in clean_ids:
                item = self._find_item(node_id)
                if item is None:
                    continue
                self._expand_item_ancestors(item)
                item.setSelected(True)
                current_item = item
            if current_item is not None:
                self._tree.setCurrentItem(current_item, 0, QItemSelectionModel.SelectionFlag.NoUpdate)
        finally:
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
        def _walk(item: Optional[QTreeWidgetItem]) -> None:
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
        def _walk(item: Optional[QTreeWidgetItem]) -> None:
            if item is None:
                return
            key = self._item_key(item)
            if key in state:
                item.setExpanded(state[key])
            for index in range(item.childCount()):
                _walk(item.child(index))
        for index in range(self._tree.topLevelItemCount()):
            _walk(self._tree.topLevelItem(index))

    def _find_item_by_key(self, item_key: Optional[str]) -> Optional[QTreeWidgetItem]:
        if not item_key:
            return None
        def _search(parent: Optional[QTreeWidgetItem]) -> Optional[QTreeWidgetItem]:
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
        item = self._find_item_by_key(item_key)
        if item is not None:
            self._expand_item_ancestors(item)
            self._tree.setCurrentItem(item)

    def _reapply_focus_view(self, preferred_selection_key: Optional[str] = None) -> None:
        target_selection = preferred_selection_key
        self._tree.blockSignals(True)
        try:
            target_selection = self._apply_focus_view(target_selection)
            if target_selection:
                self._restore_selection(target_selection)
        finally:
            self._tree.blockSignals(False)
        self._tree.viewport().update()
        self._tree.updateGeometry()

    def _apply_focus_view(self, selected_key: Optional[str]) -> Optional[str]:
        focus_key = self._focused_item_key
        focus_item = self._find_item_by_key(focus_key) if focus_key else None
        if focus_key and focus_item is None:
            self._focused_item_key = None
            focus_key = None
        visible_keys = self._focus_visible_keys(focus_item) if focus_item is not None else None
        def _walk(parent: Optional[QTreeWidgetItem]) -> None:
            count = self._tree.topLevelItemCount() if parent is None else parent.childCount()
            for index in range(count):
                item = self._tree.topLevelItem(index) if parent is None else parent.child(index)
                if item is None:
                    continue
                item_key = self._item_key(item)
                item.setHidden(bool(visible_keys is not None and item_key not in visible_keys))
                _walk(item)
        _walk(None)
        if focus_item is not None:
            self._expand_item_ancestors(focus_item)
            if focus_item.childCount() > 0:
                focus_item.setExpanded(True)
            if visible_keys and selected_key not in visible_keys:
                return self._focused_item_key
        return selected_key

    def _focus_visible_keys(self, focus_item: Optional[QTreeWidgetItem]) -> set[str]:
        visible_keys: set[str] = set()
        if focus_item is None:
            return visible_keys
        current = focus_item
        while current is not None:
            item_key = self._item_key(current)
            if item_key:
                visible_keys.add(item_key)
            current = current.parent()
        stack = [focus_item]
        while stack:
            item = stack.pop()
            item_key = self._item_key(item)
            if item_key:
                visible_keys.add(item_key)
            stack.extend(item.child(index) for index in range(item.childCount()))
        return visible_keys

    @staticmethod
    def _expand_item_ancestors(item: Optional[QTreeWidgetItem]) -> None:
        current = item
        while current is not None:
            current.setExpanded(True)
            current = current.parent()

    # ─────────────────────────────────────────────────────────
    # Size hint / 显示模式管理
    # ─────────────────────────────────────────────────────────

    def _update_wrapped_item_size_hints(self) -> None:
        viewport_width = max(180, self._tree.viewport().width())
        def _walk(item: Optional[QTreeWidgetItem], depth: int) -> None:
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

    def _update_wrapped_item_size_hint_for_item(self, item: Optional[QTreeWidgetItem]) -> None:
        if item is None:
            return
        try:
            viewport_width = max(180, self._tree.viewport().width())
            self._apply_wrapped_item_size_hint(item, viewport_width, self._item_depth(item))
        except RuntimeError:
            return

    def _reset_item_size_hints(self) -> None:
        def _walk(item: Optional[QTreeWidgetItem]) -> None:
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
    def _item_depth(item: Optional[QTreeWidgetItem]) -> int:
        depth = 0
        current = item.parent() if item is not None else None
        while current is not None:
            depth += 1
            current = current.parent()
        return depth

    def _apply_wrapped_item_size_hint(self, item: QTreeWidgetItem, viewport_width: int, depth: int) -> None:
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

    def _project_branch_toggle_key(self, item: Optional[QTreeWidgetItem], x_pos: float) -> Optional[str]:
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

    def _consume_branch_toggle_click(self, item: Optional[QTreeWidgetItem]) -> bool:
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
        parts = node_id.split("|")
        if len(parts) == 2 and parts[0] == "extension_config_group":
            return (parts[1], parts[1])
        return None

    def _cmd_create_extension_config(self, group_node_id: str) -> None:
        parsed = self._parse_extension_config_group_node_id(group_node_id)
        if parsed is None:
            return
        _category, extension_type = parsed
        base_name = self._extension_config_default_name(extension_type)
        from core.global_assets import global_assets
        config_id = global_assets.create_extension_config(extension_type, name=base_name)
        if config_id:
            self.refresh()

    def _cmd_duplicate_extension_config(self, config_id: str) -> None:
        from core.global_assets import global_assets
        config = global_assets.get_extension_config(config_id)
        if config is None:
            return
        new_id = global_assets.create_extension_config(config.extension_type, name=f"{config.name} (副本)", preset=config)
        if new_id:
            self.refresh()

    def _extension_config_default_name(self, extension_type: str) -> str:
        entry = build_extension_entry(extension_type)
        if entry:
            return getattr(entry, "name", extension_type) or extension_type
        ext_type = extension_registry.get(extension_type, {})
        if isinstance(ext_type, dict):
            return ext_type.get("name", extension_type)
        return extension_type

    @staticmethod
    def _extension_entry_for_category_type(category: str, extension_type: str) -> Optional[dict]:
        entry = build_extension_entry(extension_type)
        if entry:
            return entry
        ext_type = extension_registry.get(extension_type, {})
        if isinstance(ext_type, dict):
            return ext_type
        return None

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
