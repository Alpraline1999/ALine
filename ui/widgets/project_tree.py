"""
共享项目树组件 — ProjectTreeWidget

由 project_manager 数据驱动，可嵌入任意页面。
支持虚拟叶节点（DataSeries / Curve）、过滤模式、右键菜单、内联重命名。
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from math import ceil

from PySide6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAbstractTextDocumentLayout, QColor, QDesktopServices, QFontMetrics, QPainter, QPalette, QPen, QPixmap, QTextDocument, QTextOption
from PySide6.QtWidgets import QAbstractItemView, QApplication, QFileDialog, QStyle, QStyleOptionViewItem, QVBoxLayout, QWidget
from qfluentwidgets import (
    Action, FluentIcon as FIF, InfoBar, InfoBarPosition, MessageBox, RoundMenu, ToolTip, TreeWidget,
)
from qfluentwidgets.components.widgets.tree_view import TreeItemDelegate
from PySide6.QtWidgets import QTreeWidgetItem

from core.global_assets import ExtensionConfigPreset, global_assets, make_plot_style_asset_key, parse_plot_style_asset_key
from core.extension_api import build_extension_entry, extension_registry
from core.project_manager import project_manager
from core.ui_preferences import get_tree_name_display_mode
from models.schemas import DataFile
from ui.dialogs.fluent_dialogs import SelectionDialog, TextInputDialog


def _series_color_icon(color_str: str) -> QPixmap:
    """生成 16×16 折线图风格图标（用于 DataSeries 叶节点）。"""
    px = QPixmap(16, 16)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    color = QColor(color_str if color_str else "#0078D4")
    painter.setPen(QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    points = [QPoint(2, 11), QPoint(6, 8), QPoint(9, 10), QPoint(13, 4)]
    for left, right in zip(points, points[1:]):
        painter.drawLine(left, right)
    painter.setBrush(color)
    painter.setPen(Qt.PenStyle.NoPen)
    for point in points:
        painter.drawEllipse(point, 1.8, 1.8)
    painter.end()
    return px


def _wrap_text_height(font, text: str, width: int) -> int:
    document = QTextDocument()
    document.setDefaultFont(font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAnywhere)
    document.setDefaultTextOption(option)
    document.setPlainText(text)
    document.setTextWidth(max(1, width))
    return ceil(document.size().height())


_ROOT_GROUP_ORDER = {
    "source_files": 0,
    "datasets": 1,
    "dataset_set": 1,
    "pictures": 2,
    "picture_set": 2,
    "analysis_result_group": 3,
    "images": 4,
    "image_set": 4,
    "tools": 5,
    "tool_set": 5,
}


def _sort_name_bucket(text: str) -> int:
    clean = str(text or "").strip()
    if not clean:
        return 3
    first = clean[0]
    if first.isascii() and first.isalnum():
        return 0
    if first.isascii():
        return 1
    return 2


def _sort_text_key(text: str) -> tuple[int, str, str]:
    clean = str(text or "").strip()
    return (_sort_name_bucket(clean), clean.casefold(), clean)


def _extension_config_name_key(text: str) -> str:
    return str(text or "").strip().casefold()


def _global_asset_sort_key(asset) -> tuple[int, int, str, str]:
    builtin_rank = 0 if bool(getattr(asset, "is_builtin", False)) else 1
    name_key = _sort_text_key(getattr(asset, "name", "") or getattr(asset, "id", ""))
    return (builtin_rank, name_key[0], name_key[1], name_key[2])


_PROJECT_ICON = getattr(FIF, "ZIP_FOLDER", getattr(FIF, "LIBRARY", FIF.FOLDER))
_DATA_ICON = FIF.DICTIONARY
_SOURCE_FOLDER_ICON = getattr(FIF, "IOT", FIF.FOLDER)
_SOURCE_FILE_ICON = getattr(FIF, "DOCUMENT", FIF.FOLDER)
_DATASET_GROUP_ICON = getattr(FIF, "LIBRARY", FIF.FOLDER)
_DIGITIZE_GROUP_ICON = getattr(FIF, "LABEL", FIF.PHOTO)
_PICTURE_GROUP_ICON = getattr(FIF, "PHOTO", FIF.PHOTO)
_NEW_DATASET_ACTION_ICON = getattr(FIF, "DICTIONARY_ADD", FIF.ADD)
_IMPORT_DATA_ACTION_ICON = getattr(FIF, "DOWNLOAD", FIF.DOWNLOAD)
_OPEN_DIGITIZE_ACTION_ICON = getattr(FIF, "LABEL", FIF.EDIT)
_SOURCE_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


# ── 每种 kind 的 (FluentIcon, 颜色hint) ──────────────────────────
_KIND_CONFIG = {
    "folder":          (FIF.FOLDER,          None),
    "data_file":       (_DATA_ICON,         None),
    "source_file":     (_SOURCE_FILE_ICON,  None),
    "image_work":      (FIF.PHOTO,          None),
    "picture":         (FIF.PHOTO,           None),
    "pipeline":        (FIF.DEVELOPER_TOOLS, "#0078D4"),
    "figure_template": (FIF.PIE_SINGLE,      "#107C10"),
    "report_template": (FIF.DOCUMENT,        "#8C6C00"),
    "analysis_result": (FIF.SEARCH,          "#D83B01"),
    "ai_tool":         (FIF.CHAT,            "#881798"),   # v0.2 compat
    "ai_prompt":       (FIF.CHAT,            "#881798"),
    "ai_skill":        (FIF.DEVELOPER_TOOLS, "#881798"),
    "ai_agent":        (FIF.ROBOT,           "#881798"),
    "global_pipeline": (FIF.DEVELOPER_TOOLS, "#0078D4"),
    "global_report_template": (FIF.DOCUMENT, "#8C6C00"),
    "global_curve_style_template": (FIF.PENCIL_INK, "#107C10"),
    "global_plot_style": (FIF.PIE_SINGLE,    "#8C6C00"),
    "global_plot_theme": (FIF.PIE_SINGLE,    "#8C6C00"),
        "global_extension_config": (getattr(FIF, "SETTING", FIF.DEVELOPER_TOOLS), "#0078D4"),
    "global_ai_prompt": (FIF.CHAT,           "#881798"),
    "global_ai_skill": (FIF.DEVELOPER_TOOLS, "#881798"),
    "global_ai_agent": (FIF.ROBOT,           "#881798"),
}

# group_type → FluentIcon（系统文件夹专用图标）
_GROUP_ICON = {
    "datasets":       _DATASET_GROUP_ICON,
    "dataset_set":    _DATASET_GROUP_ICON,
    "source_files":   _SOURCE_FOLDER_ICON,
    "images":         _DIGITIZE_GROUP_ICON,
    "image_set":      FIF.PHOTO,
    "pictures":       _PICTURE_GROUP_ICON,
    "picture_set":    _PICTURE_GROUP_ICON,
    "tools":          FIF.DEVELOPER_TOOLS,
    "tool_set":       FIF.DEVELOPER_TOOLS,
    "analysis_result_group": FIF.SEARCH,
    "pipeline_group": FIF.DEVELOPER_TOOLS,
    "template_group": FIF.PIE_SINGLE,
    "figure_template_group": FIF.PIE_SINGLE,
    "report_template_group": FIF.DOCUMENT,
    "ai_group":       FIF.ROBOT,
    "prompt_group":   FIF.CHAT,
    "skill_group":    FIF.DEVELOPER_TOOLS,
    "agent_group":    FIF.ROBOT,
}

# 系统文件夹不可重命名/删除
_PROTECTED_GROUP_TYPES = frozenset({
    "datasets", "dataset_set",
    "source_files",
    "images", "image_set",
    "pictures", "picture_set",
    "tools", "tool_set",
    "analysis_result_group",
    "pipeline_group", "template_group", "figure_template_group",
    "report_template_group", "ai_group",
})

_ROOT_GROUP_TYPES = frozenset({
    "datasets", "dataset_set",
    "source_files",
    "images", "image_set",
    "pictures", "picture_set",
    "tools", "tool_set",
})

_MANAGED_FOLDER_GROUP_TYPES = frozenset({
    "datasets",
    "source_files",
    "images",
    "pictures",
    "analysis_result_group",
})

# QTreeWidgetItem UserRole 存储 (kind, id)
_ROLE = Qt.ItemDataRole.UserRole
_PROJECT_ROLE = Qt.ItemDataRole.UserRole + 1
_SYNTHETIC_GLOBAL_KINDS = frozenset({
    "global_root", "global_group", "global_pipeline",
    "global_report_template", "global_curve_style_template", "global_plot_style", "global_plot_theme", "global_extension_config",
    "global_ai_prompt", "global_ai_skill", "global_ai_agent",
})

_EXTENSION_CONFIG_GROUPS = [
    ("plot", "绘图扩展", getattr(FIF, "PENCIL_INK", FIF.DEVELOPER_TOOLS)),
    ("processing", "处理扩展", FIF.DEVELOPER_TOOLS),
    ("analysis", "分析扩展", FIF.SEARCH),
]


def _extension_config_sort_key(config) -> tuple[int, int, str, str]:
    name_key = _sort_text_key(getattr(config, "name", "") or getattr(config, "id", ""))
    return (0 if bool(getattr(config, "is_default", False)) else 1, name_key[0], name_key[1], name_key[2])


class _ProjectTreeView(TreeWidget):
    def __init__(self, owner: "ProjectTreeWidget", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._owner = owner

    def startDrag(self, supportedActions) -> None:
        self._owner._remember_drag_source_item(self.currentItem())
        super().startDrag(supportedActions)

    def dropEvent(self, event) -> None:
        source_item = self._owner._drag_source_item_for_drop(self.currentItem())
        target_item = self.itemAt(event.position().toPoint())
        try:
            if self._owner._perform_drop_move(source_item, target_item, defer_view_refresh=True):
                event.acceptProposedAction()
                return
            event.ignore()
        finally:
            self._owner._clear_drag_source_item()


class _ProjectTreeWrapAnywhereDelegate(TreeItemDelegate):
    def __init__(self, owner: "ProjectTreeWidget", parent: "_ProjectTreeView"):
        super().__init__(parent)
        self._owner = owner

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        if self._owner._name_display_mode != "wrap":
            super().paint(painter, option, index)
            return

        item_option = QStyleOptionViewItem(option)
        self.initStyleOption(item_option, index)
        text = item_option.text
        if not text:
            super().paint(painter, option, index)
            return

        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        item_option.text = ""
        style = item_option.widget.style() if item_option.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, item_option, painter, item_option.widget)

        if index.data(Qt.ItemDataRole.CheckStateRole) is not None:
            self._drawCheckBox(painter, item_option, index)

        if item_option.state & (QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver):
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            self._drawBackground(painter, item_option, index)
            self._drawIndicator(painter, item_option, index)
            painter.restore()

        text_rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, item_option, item_option.widget)
        if not text_rect.isValid() or text_rect.width() <= 0:
            return

        document = QTextDocument()
        document.setDefaultFont(item_option.font)
        text_option = QTextOption()
        text_option.setWrapMode(QTextOption.WrapMode.WrapAnywhere)
        text_option.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        document.setDefaultTextOption(text_option)
        document.setPlainText(text)
        document.setTextWidth(max(1, text_rect.width()))

        palette = QPalette(item_option.palette)
        foreground = index.data(Qt.ItemDataRole.ForegroundRole)
        if item_option.state & QStyle.StateFlag.State_Selected:
            text_color = palette.color(QPalette.ColorRole.HighlightedText)
        elif hasattr(foreground, "color"):
            text_color = foreground.color()
        else:
            text_color = palette.color(QPalette.ColorRole.Text)

        paint_context = QAbstractTextDocumentLayout.PaintContext()
        paint_context.palette = QPalette(palette)
        paint_context.palette.setColor(QPalette.ColorRole.Text, text_color)
        paint_context.palette.setColor(QPalette.ColorRole.WindowText, text_color)
        paint_context.palette.setColor(QPalette.ColorRole.HighlightedText, text_color)

        content_height = document.size().height()
        y_offset = text_rect.top() + max(0.0, (text_rect.height() - content_height) / 2.0)
        painter.save()
        painter.setClipRect(text_rect)
        painter.translate(text_rect.left(), y_offset)
        document.documentLayout().draw(painter, paint_context)
        painter.restore()


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

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._filter_kinds: List[str] = []  # 空 = 显示全部
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tree = _ProjectTreeView(self, self)
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
        self._tree.setItemDelegate(_ProjectTreeWrapAnywhereDelegate(self, self._tree))

        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemActivated.connect(self._on_item_activated)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._tree.viewport().installEventFilter(self)

        layout.addWidget(self._tree)

        self._renaming = False  # 防止 itemChanged 循环
        self._branch_toggle_item_key: Optional[str] = None
        self._drag_source_item_key: Optional[str] = None
        self._fluent_tooltip: Optional[ToolTip] = None
        self._name_display_mode = "elide"
        self.set_name_display_mode(get_tree_name_display_mode())

    # ─────────────────────────────────────────────────────────
    # 公开接口
    # ─────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """从 project_manager.projects 完整重建树。"""
        expansion_state = self._capture_expansion_state()
        selected_key = self._current_item_key()
        self._tree.blockSignals(True)
        self._tree.clear()
        if not project_manager.projects:
            self._build_global_assets_root()
            self._restore_expansion_state(expansion_state)
            self._restore_selection(selected_key)
            self._tree.blockSignals(False)
            return

        for project in project_manager.projects:
            if project.tree is None:
                continue
            project_item = QTreeWidgetItem([project.name])
            project_item.setData(0, _ROLE, ("project", project.id))
            project_item.setData(0, _PROJECT_ROLE, project.id)
            project_item.setIcon(0, _PROJECT_ICON.icon())
            project_item.setToolTip(0, project.name)
            if project.id == project_manager.current_project_id:
                font = project_item.font(0)
                font.setBold(True)
                project_item.setFont(0, font)
            self._tree.addTopLevelItem(project_item)
            self._build_children(project, None, project_item)
            project_item.setExpanded(True)
        self._build_global_assets_root()
        self._restore_expansion_state(expansion_state)
        self._restore_selection(selected_key)
        self._apply_name_display_mode()
        self._tree.blockSignals(False)
        self._tree.viewport().update()
        self._tree.updateGeometry()
        if self._name_display_mode == "wrap":
            QTimer.singleShot(0, self._update_wrapped_item_size_hints)

    def expand_all_items(self) -> None:
        self._expand_all_items()

    def collapse_all_items(self) -> None:
        self._collapse_all_items()

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

    def set_filter_kinds(self, kinds: List[str]) -> None:
        """只显示指定 kind 的节点（空列表 = 显示全部）。"""
        self._filter_kinds = list(kinds)
        self.refresh()

    def set_name_display_mode(self, mode: str) -> None:
        self._name_display_mode = "elide" if mode == "elide" else "wrap"
        self._apply_name_display_mode()

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
            return self._can_edit_global_asset(kind, node_id)
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
            return self._can_edit_global_asset(kind, node_id)
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
        title = title_map.get(kind, "重命名节点")
        new_name, ok = TextInputDialog.get_text(self._dialog_parent(), title, "名称:", text=current_name)
        if not ok or not new_name.strip():
            return
        clean_name = new_name.strip()
        if kind in _SYNTHETIC_GLOBAL_KINDS:
            changed = self._rename_global_asset(kind, node_id, clean_name)
            if changed:
                self.refresh()
                self.project_modified.emit()
            return
        if kind == "series":
            changed = project_manager.rename_series(node_id, clean_name)
        elif kind == "curve":
            changed = project_manager.rename_curve(node_id, clean_name)
        else:
            changed = project_manager.rename_node(node_id, clean_name)
        if changed:
            self.refresh()
            self.select_node(node_id)
            self.project_modified.emit()
            return
        InfoBar.warning(
            "重命名失败",
            project_manager.get_last_error_message() or "名称已存在或当前节点不支持重命名",
            parent=self,
            position=InfoBarPosition.TOP,
        )

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

        curve_styles = self._make_synthetic_item("曲线样式", "global_group", "__global_curve_styles__", FIF.PENCIL_INK)
        for item in sorted(global_assets.list_curve_style_templates(), key=_global_asset_sort_key):
            curve_styles.addChild(self._make_synthetic_item(item.name, "global_curve_style_template", item.id, FIF.PENCIL_INK))
        root.addChild(curve_styles)

        plot_themes = self._make_synthetic_item("绘图样式", "global_group", "__global_plot_styles__", FIF.PIE_SINGLE)
        for item in sorted(global_assets.list_plot_themes(include_builtin=True), key=_global_asset_sort_key):
            plot_themes.addChild(self._make_synthetic_item(
                item.name,
                "global_plot_style",
                make_plot_style_asset_key("theme", item.id or item.name),
                FIF.PIE_SINGLE,
            ))
        for item in sorted(global_assets.list_figure_templates(), key=lambda asset: _sort_text_key(asset.name or asset.id)):
            plot_themes.addChild(self._make_synthetic_item(
                item.name or item.id[:8],
                "global_plot_style",
                make_plot_style_asset_key("template", item.id),
                FIF.PIE_SINGLE,
            ))
        root.addChild(plot_themes)

        reports = self._make_synthetic_item("报告模板", "global_group", "__global_reports__", FIF.DOCUMENT)
        for item in sorted(global_assets.list_report_templates(include_builtin=True), key=_global_asset_sort_key):
            reports.addChild(self._make_synthetic_item(item.name, "global_report_template", item.id, FIF.DOCUMENT))
        root.addChild(reports)

        extension_configs = self._make_synthetic_item(
            "扩展配置",
            "global_group",
            "__global_extension_configs__",
            getattr(FIF, "SETTING", FIF.DEVELOPER_TOOLS),
        )
        for category, label, icon in _EXTENSION_CONFIG_GROUPS:
            category_item = self._make_synthetic_item(
                label,
                "global_group",
                f"__global_extension_configs__:{category}",
                icon,
            )
            for extension_item in self._build_extension_config_group_items(category):
                category_item.addChild(extension_item)
            extension_configs.addChild(category_item)
        root.addChild(extension_configs)

        root.setExpanded(True)
        for index in range(root.childCount()):
            root.child(index).setExpanded(True)
        self._tree.addTopLevelItem(root)

    def _build_extension_config_group_items(self, category: str) -> List[QTreeWidgetItem]:
        if category == "plot":
            entries = [build_extension_entry(extension) for extension in extension_registry.list_plot()]
        elif category == "processing":
            entries = [build_extension_entry(extension) for extension in extension_registry.list_processing()]
        else:
            entries = [build_extension_entry(extension) for extension in extension_registry.list_analysis()]

        entry_by_type: Dict[str, dict] = {}
        for entry in entries:
            type_id = str(entry.get("type") or "").strip()
            if not type_id or not entry.get("listed", True):
                continue
            entry_by_type[type_id] = dict(entry)
            global_assets.ensure_extension_default_config(
                category,
                type_id,
                str(entry.get("name") or type_id),
                dict(entry.get("resolved_options") or {}),
            )

        grouped_configs: Dict[str, List[ExtensionConfigPreset]] = {type_id: [] for type_id in entry_by_type}
        for item in global_assets.list_extension_configs(category=category, include_defaults=False):
            type_id = str(item.extension_type or "").strip()
            if not type_id or type_id not in entry_by_type:
                continue
            grouped_configs.setdefault(type_id, []).append(item)

        items: List[QTreeWidgetItem] = []
        sorted_type_ids = sorted(
            entry_by_type.keys(),
            key=lambda value: _sort_text_key(
                str(entry_by_type.get(value, {}).get("name") or value)
            ),
        )
        display_names = {
            type_id: str(entry_by_type.get(type_id, {}).get("name") or type_id)
            for type_id in sorted_type_ids
        }
        duplicate_counts: Dict[str, int] = {}
        for display_name in display_names.values():
            duplicate_key = _extension_config_name_key(display_name)
            duplicate_counts[duplicate_key] = duplicate_counts.get(duplicate_key, 0) + 1

        for type_id in sorted_type_ids:
            extension_name = display_names[type_id]
            extension_label = extension_name
            if duplicate_counts.get(_extension_config_name_key(extension_name), 0) > 1:
                extension_label = f"{extension_name}（{type_id}）"
            configs = sorted(grouped_configs.get(type_id, []), key=_extension_config_sort_key)
            extension_item = self._make_synthetic_item(
                extension_label,
                "global_group",
                f"__global_extension_configs__:{category}:{type_id}",
                getattr(FIF, "SETTING", FIF.DEVELOPER_TOOLS),
            )
            for config in configs:
                extension_item.addChild(
                    self._make_synthetic_item(
                        config.name,
                        "global_extension_config",
                        config.id,
                        getattr(FIF, "SETTING", FIF.DEVELOPER_TOOLS),
                    )
                )
            items.append(extension_item)
        return items

    @staticmethod
    def _parse_extension_config_group_node_id(node_id: str) -> Optional[Tuple[str, str]]:
        parts = str(node_id or "").split(":", 2)
        if len(parts) != 3 or parts[0] != "__global_extension_configs__":
            return None
        category = parts[1].strip().lower()
        extension_type = parts[2].strip()
        if not category or not extension_type:
            return None
        return category, extension_type

    @staticmethod
    def _extension_entry_for_category_type(category: str, extension_type: str) -> Optional[dict]:
        normalized_category = str(category or "").strip().lower()
        clean_type = str(extension_type or "").strip()
        if not normalized_category or not clean_type:
            return None
        if normalized_category == "plot":
            extension = extension_registry.get_plot(clean_type)
        elif normalized_category == "processing":
            extension = extension_registry.get_processing(clean_type)
        elif normalized_category == "analysis":
            extension = extension_registry.get_analysis(clean_type)
        else:
            extension = None
        if extension is None:
            return None
        entry = build_extension_entry(extension)
        return dict(entry) if entry.get("listed", True) else None

    @staticmethod
    def _next_extension_config_name(category: str, extension_type: str, base_name: str) -> str:
        clean_base = str(base_name or "").strip() or "新配置"
        candidate = clean_base
        suffix = 2
        while global_assets.get_extension_config_by_name(category, extension_type, candidate) is not None:
            candidate = f"{clean_base} {suffix}"
            suffix += 1
        return candidate

    def _cmd_create_extension_config(self, group_node_id: str) -> None:
        group_info = self._parse_extension_config_group_node_id(group_node_id)
        if group_info is None:
            return
        category, extension_type = group_info
        entry = self._extension_entry_for_category_type(category, extension_type)
        if entry is None:
            InfoBar.warning("新建失败", "当前扩展未注册，无法创建配置", parent=self._dialog_parent(), position=InfoBarPosition.TOP)
            return
        default_name = self._next_extension_config_name(category, extension_type, "新配置")
        name, ok = TextInputDialog.get_text(self._dialog_parent(), "新建扩展配置", "配置名称:", text=default_name)
        if not ok:
            return
        try:
            saved = global_assets.add_extension_config(
                category=category,
                extension_type=extension_type,
                extension_name=str(entry.get("name") or extension_type),
                extension_version=str(entry.get("version") or ""),
                name=name,
                options=dict(entry.get("resolved_options") or {}),
            )
        except ValueError as exc:
            InfoBar.warning("新建失败", str(exc), parent=self._dialog_parent(), position=InfoBarPosition.TOP)
            return
        self.refresh()
        self.project_modified.emit()
        self.node_activated.emit("global_extension_config", saved.id)

    def _cmd_duplicate_extension_config(self, config_id: str) -> None:
        config_item = global_assets.get_extension_config(config_id)
        if config_item is None:
            return
        category = str(config_item.category or "").strip().lower()
        extension_type = str(config_item.extension_type or "").strip()
        if not category or not extension_type:
            return
        entry = self._extension_entry_for_category_type(category, extension_type)
        default_name = self._next_extension_config_name(category, extension_type, f"{config_item.name} 副本")
        name, ok = TextInputDialog.get_text(self._dialog_parent(), "创建配置副本", "配置名称:", text=default_name)
        if not ok:
            return
        try:
            saved = global_assets.add_extension_config(
                category=category,
                extension_type=extension_type,
                extension_name=str((entry or {}).get("name") or config_item.extension_name or extension_type),
                extension_version=str((entry or {}).get("version") or config_item.extension_version or ""),
                name=name,
                options=dict(config_item.options or {}),
            )
        except ValueError as exc:
            InfoBar.warning("创建副本失败", str(exc), parent=self._dialog_parent(), position=InfoBarPosition.TOP)
            return
        self.refresh()
        self.project_modified.emit()
        self.node_activated.emit("global_extension_config", saved.id)

    def _make_item(self, node, project_id: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([node.name])
        item.setData(0, _ROLE, (node.kind, node.id))
        item.setData(0, _PROJECT_ROLE, project_id)
        item.setToolTip(0, node.name)

        # 系统文件夹不可内联编辑
        group_type = self._canonical_group_type(getattr(node, "group_type", None))
        is_protected = self._is_protected_folder(node)
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if node.kind == "folder":
            flags |= Qt.ItemFlag.ItemIsDropEnabled
            if not is_protected:
                flags |= Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsDragEnabled
        else:
            flags |= Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsEditable
            if node.kind in {"data_file", "image_work"}:
                flags |= Qt.ItemFlag.ItemIsDropEnabled
        item.setFlags(flags)

        # 图标选择
        if node.kind == "folder":
            icon_fif = self._folder_icon(node, group_type)
            item.setIcon(0, icon_fif.icon())
        else:
            cfg = _KIND_CONFIG.get(node.kind, (FIF.DOCUMENT, None))
            if node.kind == "source_file":
                cfg = (self._source_file_icon(node), cfg[1])
            icon_fif, _color_hint = cfg
            if icon_fif is not None:
                item.setIcon(0, icon_fif.icon())
        return item

    def _make_virtual_series_item(self, series, project_id: str) -> QTreeWidgetItem:
        """创建 DataSeries 虚拟叶节点（不存储在 project.tree 中）。"""
        label = series.name or series.id[:8]
        item = QTreeWidgetItem([label])
        item.setData(0, _ROLE, ("series", series.id))
        item.setData(0, _PROJECT_ROLE, project_id)
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled |
            Qt.ItemFlag.ItemIsSelectable |
            Qt.ItemFlag.ItemIsDragEnabled
        )
        item.setIcon(0, _series_color_icon(series.color or "#0078D4"))
        item.setToolTip(0, label)
        return item

    def _make_virtual_curve_item(self, curve, project_id: str) -> QTreeWidgetItem:
        """创建 Curve 虚拟叶节点。"""
        label = curve.name or curve.id[:8]
        item = QTreeWidgetItem([label])
        item.setData(0, _ROLE, ("curve", curve.id))
        item.setData(0, _PROJECT_ROLE, project_id)
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled |
            Qt.ItemFlag.ItemIsSelectable |
            Qt.ItemFlag.ItemIsDragEnabled
        )
        item.setIcon(0, FIF.PENCIL_INK.icon())
        item.setToolTip(0, label)
        return item

    def _tree_node_sort_key(self, node, parent_id: Optional[str]) -> tuple[int, int, str, str]:
        group_type = self._canonical_group_type(getattr(node, "group_type", None))
        if parent_id is None and node.kind == "folder" and group_type in _ROOT_GROUP_ORDER:
            return (-1, _ROOT_GROUP_ORDER[group_type], "", "")
        name_key = _sort_text_key(getattr(node, "name", "") or "")
        folder_rank = 0 if node.kind == "folder" else 1
        return (folder_rank, name_key[0], name_key[1], name_key[2])

    def _activate_item_project(self, item: Optional[QTreeWidgetItem]) -> None:
        if item is None:
            return
        try:
            project_id = item.data(0, _PROJECT_ROLE)
        except RuntimeError:
            return
        if project_id and project_id != project_manager.current_project_id:
            project_manager.set_current_project(project_id)

    # ─────────────────────────────────────────────────────────
    # 信号处理
    # ─────────────────────────────────────────────────────────

    def _on_item_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        if self._consume_branch_toggle_click(item):
            return
        self._activate_item_project(item)
        d = self._item_role_data(item)
        if d:
            self.node_selected.emit(d[0], d[1])

    def _on_item_activated(self, item: QTreeWidgetItem, _col: int) -> None:
        if self._consume_branch_toggle_click(item):
            return
        self._activate_item_project(item)
        d = self._item_role_data(item)
        if d:
            self.node_activated.emit(d[0], d[1])

    def eventFilter(self, watched, event):
        if watched is self._tree.viewport():
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                item = self._tree.itemAt(event.position().toPoint())
                self._branch_toggle_item_key = self._project_branch_toggle_key(item, event.position().x())
                self._remember_drag_source_item(item)
            elif event.type() in {
                QEvent.Type.MouseButtonDblClick,
                QEvent.Type.Leave,
            }:
                self._branch_toggle_item_key = None
                self._hide_fluent_tooltip()
            elif event.type() == QEvent.Type.ToolTip:
                self._show_fluent_tooltip_for_event(event)
                return True
            elif event.type() == QEvent.Type.MouseButtonPress:
                self._hide_fluent_tooltip()
            elif event.type() == QEvent.Type.Resize:
                if self._name_display_mode == "wrap":
                    self._update_wrapped_item_size_hints()
        return super().eventFilter(watched, event)

    def _on_item_changed(self, item: QTreeWidgetItem, _col: int) -> None:
        if self._renaming:
            return
        self._activate_item_project(item)
        d = self._item_role_data(item)
        if not d:
            return
        kind, node_id = d
        if kind in ("series", "curve") or kind in _SYNTHETIC_GLOBAL_KINDS:
            return  # 虚拟节点，不可重命名
        new_name = item.text(0).strip()
        if not new_name:
            return
        previous_name = item.toolTip(0) or item.text(0)
        self._renaming = True
        changed = project_manager.rename_node(node_id, new_name)
        if not changed:
            current_node = project_manager.get_node_by_id(node_id)
            restored_name = getattr(current_node, "name", "") or previous_name
            item.setText(0, restored_name)
            item.setToolTip(0, restored_name)
        else:
            item.setToolTip(0, new_name)
        self._renaming = False
        if not changed:
            InfoBar.warning(
                "重命名失败",
                project_manager.get_last_error_message() or "当前节点重命名失败",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return
        if self._name_display_mode == "wrap":
            self._update_wrapped_item_size_hint_for_item(item)
            QTimer.singleShot(0, self._update_wrapped_item_size_hints)
        else:
            item.setSizeHint(0, QSize())
        self._tree.viewport().update()
        self._tree.updateGeometry()
        self.project_modified.emit()

    # ─────────────────────────────────────────────────────────
    # 右键菜单
    # ─────────────────────────────────────────────────────────

    def _on_context_menu(self, pos) -> None:
        item = self._tree.itemAt(pos)
        if item is None:
            menu = RoundMenu(parent=self._dialog_parent())
            self._append_tree_scope_actions(menu)
            menu.exec(self._tree.viewport().mapToGlobal(pos))
            return

        selected_items = self._selected_items_for_context_menu(item)
        self._activate_item_project(item)
        menu = RoundMenu(parent=self._dialog_parent())

        batch_payloads = self._batch_action_payloads(selected_items)
        if len(batch_payloads) > 1:
            manage_entries = [
                (FIF.DELETE, f"删除选中 {len(batch_payloads)} 项", lambda: self._cmd_delete_batch(batch_payloads)),
            ]
            move_choices = self._common_batch_move_choices(batch_payloads)
            if move_choices:
                manage_entries.append((FIF.SYNC, f"移动选中 {len(batch_payloads)} 项...", lambda: self._cmd_move_batch(batch_payloads, move_choices)))
            self._append_menu_section(menu, manage_entries)
            self._append_tree_scope_actions(menu, separated=True)
            menu.exec(self._tree.viewport().mapToGlobal(pos))
            return

        d = item.data(0, _ROLE)
        if not d:
            return
        kind, node_id = d

        if kind == "project":
            self._append_tree_scope_actions(menu)
            menu.exec(self._tree.viewport().mapToGlobal(pos))
            return

        import_entries: List[Tuple[object, str, object]] = []
        manage_entries: List[Tuple[object, str, object]] = []

        if kind in _SYNTHETIC_GLOBAL_KINDS:
            if kind == "global_pipeline":
                manage_entries.append((FIF.DEVELOPER_TOOLS, "加载到处理页", lambda: self.node_activated.emit(kind, node_id)))
            elif kind == "global_report_template":
                manage_entries.append((FIF.DOCUMENT, "应用到分析页", lambda: self.node_activated.emit(kind, node_id)))
            elif kind == "global_curve_style_template":
                manage_entries.append((FIF.PENCIL_INK, "应用到可视化", lambda: self.node_activated.emit(kind, node_id)))
            elif kind in ("global_plot_style", "global_plot_theme"):
                manage_entries.append((FIF.PIE_SINGLE, "应用到可视化", lambda: self.node_activated.emit(kind, node_id)))
            elif kind == "global_group":
                if self._parse_extension_config_group_node_id(node_id) is not None:
                    manage_entries.append((FIF.ADD, "新建配置", lambda: self._cmd_create_extension_config(node_id)))
            elif kind == "global_extension_config":
                manage_entries.append((getattr(FIF, "SETTING", FIF.DEVELOPER_TOOLS), "在数据管理页查看/编辑", lambda: self.node_activated.emit(kind, node_id)))
                manage_entries.append((FIF.COPY, "创建副本", lambda: self._cmd_duplicate_extension_config(node_id)))
            elif kind in ("global_ai_prompt", "global_ai_skill", "global_ai_agent"):
                manage_entries.append((FIF.EDIT, "在设置中查看", lambda: self.node_activated.emit(kind, node_id)))
            if self._can_edit_global_asset(kind, node_id):
                manage_entries.extend([
                    (FIF.EDIT, "重命名", lambda: self._cmd_rename_global(kind, node_id, item.text(0))),
                    (FIF.DELETE, "删除", lambda: self._cmd_delete_global(kind, node_id, item.text(0))),
                ])
            self._append_menu_section(menu, manage_entries)
            if menu.actions():
                self._append_tree_scope_actions(menu, separated=True)
                menu.exec(self._tree.viewport().mapToGlobal(pos))
            return

        if kind == "folder":
            node = project_manager.get_node_by_id(node_id)
            is_protected = self._is_protected_folder(node)
            managed_group_type = self._folder_collection_group(node_id)
            if managed_group_type in _MANAGED_FOLDER_GROUP_TYPES:
                if managed_group_type == "datasets":
                    import_entries.append((_NEW_DATASET_ACTION_ICON, "新建数据集", lambda: self._cmd_add_dataset_node(node_id)))
                    import_entries.append((_IMPORT_DATA_ACTION_ICON, "导入数据文件...", lambda: self._cmd_import_data_file(node_id)))
                if managed_group_type == "source_files":
                    import_entries.append((FIF.DOWNLOAD, "批量导入源文件...", lambda: self._cmd_import_source_files(node_id)))
                if managed_group_type == "images":
                    import_entries.append((FIF.PHOTO, "导入图片...", lambda: self._cmd_import_digitize_images(node_id)))
                import_entries.append((FIF.FOLDER_ADD, "新建子文件夹", lambda: self._cmd_add_child_folder(node_id)))
                if managed_group_type == "pictures":
                    manage_entries.append((_PICTURE_GROUP_ICON, "在文件夹打开", lambda: self._open_picture_folder(node_id)))
                elif managed_group_type == "source_files":
                    manage_entries.append((_SOURCE_FOLDER_ICON, "在文件夹打开", lambda: self._open_source_file_folder(node_id)))
            if not is_protected:
                manage_entries.extend([
                    (FIF.EDIT, "重命名", lambda: self.rename_selected_item()),
                    (FIF.DELETE, "删除", lambda: self._cmd_delete(node_id, item.text(0))),
                ])
            if managed_group_type in _MANAGED_FOLDER_GROUP_TYPES:
                manage_entries.append((FIF.SYNC, "清理空子文件夹", lambda: self._cmd_prune_empty_folders(node_id, scope_label=item.text(0))))

        elif kind == "data_file":
            move_choices = self._move_target_choices(kind, node_id)
            manage_entries.extend([
                (FIF.PIE_SINGLE, "发送到可视化", lambda: self.node_activated.emit("data_file_to_chart", node_id)),
                (FIF.DEVELOPER_TOOLS, "发送到处理", lambda: self.node_activated.emit("data_file_to_process", node_id)),
                (FIF.SEARCH, "发送到分析", lambda: self.node_activated.emit("data_file_to_analysis", node_id)),
                (FIF.EDIT, "重命名", lambda: self.rename_selected_item()),
                (FIF.DELETE, "删除", lambda: self._cmd_delete(node_id, item.text(0))),
            ])
            if move_choices:
                manage_entries.append((FIF.SYNC, "移动到...", lambda: self._cmd_move_virtual(kind, node_id, move_choices)))

        elif kind == "source_file":
            move_choices = self._move_target_choices(kind, node_id)
            import_entries.extend([
                (_IMPORT_DATA_ACTION_ICON, "导入到数据集", lambda: self.node_activated.emit("source_file_to_data", node_id)),
                (FIF.PHOTO, "导入到数字化", lambda: self.node_activated.emit("source_file_to_digitize", node_id)),
            ])
            manage_entries.extend([
                (_SOURCE_FOLDER_ICON, "在文件夹打开", lambda: self._open_source_file_folder(node_id, source_node=True)),
                (FIF.EDIT, "重命名", lambda: self.rename_selected_item()),
                (FIF.DELETE, "删除", lambda: self._cmd_delete(node_id, item.text(0))),
            ])
            if move_choices:
                manage_entries.append((FIF.SYNC, "移动到...", lambda: self._cmd_move_virtual(kind, node_id, move_choices)))

        elif kind == "series":
            move_choices = self._move_target_choices(kind, node_id)
            manage_entries.extend([
                (FIF.PIE_SINGLE, "发送到可视化", lambda: self.node_activated.emit("series_to_chart", node_id)),
                (FIF.DEVELOPER_TOOLS, "发送到处理", lambda: self.node_activated.emit("series_to_process", node_id)),
                (FIF.SEARCH, "发送到分析", lambda: self.node_activated.emit("series_to_analysis", node_id)),
                (FIF.EDIT, "重命名", lambda: self.rename_selected_item()),
                (FIF.DELETE, "删除", lambda: self._cmd_delete_virtual(kind, node_id, item.text(0))),
            ])
            if move_choices:
                manage_entries.append((FIF.SYNC, "移动到...", lambda: self._cmd_move_virtual(kind, node_id, move_choices)))

        elif kind == "image_work":
            move_choices = self._move_target_choices(kind, node_id)
            manage_entries.extend([
                (FIF.ADD, "新增曲线", lambda: self.node_activated.emit("image_work_add_curve", node_id)),
                (_OPEN_DIGITIZE_ACTION_ICON, "打开取点", lambda: self.node_activated.emit("image_work", node_id)),
                # (FIF.PIE_SINGLE, "发送到可视化", lambda: self.node_activated.emit("image_work_to_chart", node_id)),
                (FIF.EDIT, "重命名", lambda: self.rename_selected_item()),
                (FIF.DELETE, "删除", lambda: self._cmd_delete(node_id, item.text(0))),
            ])
            if move_choices:
                manage_entries.append((FIF.SYNC, "移动到...", lambda: self._cmd_move_virtual(kind, node_id, move_choices)))

        elif kind == "picture":
            move_choices = self._move_target_choices(kind, node_id)
            manage_entries.extend([
                (FIF.PIE_SINGLE, "发送到可视化", lambda: self.node_activated.emit("picture_to_chart", node_id)),
                (_PICTURE_GROUP_ICON, "在文件夹打开", lambda: self._open_picture_folder(node_id, picture_node=True)),
                (FIF.EDIT, "重命名", lambda: self.rename_selected_item()),
                (FIF.DELETE, "删除", lambda: self._cmd_delete(node_id, item.text(0))),
            ])
            if move_choices:
                manage_entries.append((FIF.SYNC, "移动到...", lambda: self._cmd_move_virtual(kind, node_id, move_choices)))

        elif kind == "curve":
            move_choices = self._move_target_choices(kind, node_id)
            manage_entries.extend([
                (_IMPORT_DATA_ACTION_ICON, "导出为数据列", lambda: self.node_activated.emit("curve_export_to_data_file", node_id)),
                (FIF.PIE_SINGLE, "发送到可视化", lambda: self.node_activated.emit("curve_to_chart", node_id)),
                (FIF.EDIT, "重命名", lambda: self.rename_selected_item()),
                (FIF.DELETE, "删除", lambda: self._cmd_delete_virtual(kind, node_id, item.text(0))),
            ])
            if move_choices:
                manage_entries.append((FIF.SYNC, "移动到...", lambda: self._cmd_move_virtual(kind, node_id, move_choices)))

        elif kind == "pipeline":
            manage_entries.extend([
                (FIF.DEVELOPER_TOOLS, "加载到处理页", lambda: self.node_activated.emit("pipeline", node_id)),
                (FIF.EDIT, "重命名", lambda: self.rename_selected_item()),
                (FIF.DELETE, "删除", lambda: self._cmd_delete(node_id, item.text(0))),
            ])

        elif kind == "figure_template":
            manage_entries.extend([
                (FIF.PIE_SINGLE, "加载到可视化", lambda: self.node_activated.emit("figure_template", node_id)),
                (FIF.EDIT, "重命名", lambda: self.rename_selected_item()),
                (FIF.DELETE, "删除", lambda: self._cmd_delete(node_id, item.text(0))),
            ])

        elif kind == "report_template":
            manage_entries.extend([
                (FIF.SEARCH, "加载到分析页", lambda: self.node_activated.emit("report_template", node_id)),
                (FIF.EDIT, "重命名", lambda: self.rename_selected_item()),
                (FIF.DELETE, "删除", lambda: self._cmd_delete(node_id, item.text(0))),
            ])

        elif kind == "analysis_result":
            move_choices = self._move_target_choices(kind, node_id)
            manage_entries.extend([
                (FIF.SEARCH, "发送到分析页", lambda: self.node_activated.emit("analysis_result", node_id)),
                (FIF.EDIT, "重命名", lambda: self.rename_selected_item()),
                (FIF.DELETE, "删除", lambda: self._cmd_delete(node_id, item.text(0))),
            ])
            if move_choices:
                manage_entries.append((FIF.SYNC, "移动到...", lambda: self._cmd_move_virtual(kind, node_id, move_choices)))

        elif kind in ("ai_prompt", "ai_skill", "ai_agent", "ai_tool"):
            manage_entries.extend([
                (FIF.EDIT, "编辑", lambda: self.node_activated.emit(kind, node_id)),
                (FIF.DELETE, "删除", lambda: self._cmd_delete(node_id, item.text(0))),
            ])

        self._append_menu_section(menu, import_entries)
        self._append_menu_section(menu, manage_entries)

        if menu.actions():
            self._append_tree_scope_actions(menu, separated=True)
            menu.exec(self._tree.viewport().mapToGlobal(pos))

    # ─────────────────────────────────────────────────────────
    # 命令
    # ─────────────────────────────────────────────────────────

    def _cmd_delete(self, node_id: str, node_name: str) -> None:
        box = MessageBox("确认删除", f'确定要删除「{node_name}」及其所有内容吗？', self._dialog_parent())
        if box.exec():
            project_manager.delete_node(node_id)
            self.refresh()
            self.project_modified.emit()

    def _cmd_add_child_folder(self, parent_id: str) -> None:
        name, ok = TextInputDialog.get_text(self._dialog_parent(), "新建子文件夹", "文件夹名称:", placeholder="输入子文件夹名称")
        if not ok:
            return
        folder = self._create_child_folder(parent_id, name)
        if folder is None:
            InfoBar.warning(
                "创建失败",
                project_manager.get_last_error_message() or "未能创建子文件夹",
                parent=self._dialog_parent(),
                position=InfoBarPosition.TOP,
            )
            return
        self.refresh()
        self.select_node(folder.id)
        self.project_modified.emit()

    def _cmd_add_dataset_node(self, parent_id: str) -> None:
        from models.schemas import DataFile

        name, ok = TextInputDialog.get_text(self._dialog_parent(), "新建数据集", "数据集名称:", placeholder="输入数据集名称")
        if not ok:
            return
        clean_name = name.strip()
        if not clean_name:
            return
        node = project_manager.add_data_file(DataFile(name=clean_name), parent_id=parent_id)
        if node is None:
            InfoBar.warning(
                "创建失败",
                project_manager.get_last_error_message() or "未能创建新的数据集",
                parent=self._dialog_parent(),
                position=InfoBarPosition.TOP,
            )
            return
        self.refresh()
        self.select_node(node.id)
        self.project_modified.emit()

    def _cmd_import_data_file(self, parent_id: Optional[str] = None) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self._dialog_parent(),
            "导入数据文件",
            "",
            "数据文件 (*.csv *.txt *.dat *.tsv *.xlsx *.xls *.json *.npy *.npz);;所有文件 (*)",
        )
        if not file_path:
            return
        if not self._supports_source_file_dataset_import(file_path):
            InfoBar.warning(
                "导入失败",
                "当前文件类型不支持导入为数据文件",
                parent=self._dialog_parent(),
                position=InfoBarPosition.TOP,
            )
            return
        try:
            dialog = self._create_source_file_import_dialog(file_path)
        except Exception as exc:
            InfoBar.warning(
                "导入失败",
                f"无法读取文件: {exc}",
                parent=self._dialog_parent(),
                position=InfoBarPosition.TOP,
            )
            return
        if not dialog.exec():
            return
        selected_node_id = self._apply_source_file_import_dialog_results(dialog, target_folder_id=parent_id)
        if not selected_node_id:
            return
        self.refresh()
        self.select_node(selected_node_id)
        self.project_modified.emit()

    def _cmd_import_source_files(self, parent_id: Optional[str] = None) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self._dialog_parent(),
            "导入源文件",
            "",
            "所有文件 (*.*)",
        )
        clean_paths = [path for path in paths if path]
        if not clean_paths:
            return
        nodes = project_manager.add_source_files(clean_paths, parent_id=parent_id, auto_rename_on_conflict=True)
        if not nodes:
            InfoBar.warning(
                "导入失败",
                project_manager.get_last_error_message() or "未能导入任何源文件",
                parent=self._dialog_parent(),
                position=InfoBarPosition.TOP,
            )

    def _cmd_import_digitize_images(self, parent_id: Optional[str] = None) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self._dialog_parent(),
            "导入图片到数字化",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp);;所有文件 (*)",
        )
        clean_paths = [path for path in paths if path]
        if not clean_paths:
            return

        imported_node_ids: List[str] = []
        failed_paths: List[str] = []
        for path in clean_paths:
            if not self._supports_source_file_digitize_import(path):
                failed_paths.append(Path(path).name)
                continue
            try:
                image = project_manager.add_image(path, name=Path(path).name, parent_id=parent_id)
            except (FileNotFoundError, ValueError):
                failed_paths.append(Path(path).name)
                continue
            node_id = self._linked_tree_node_id("image_work", "image_work_id", image.id)
            if node_id:
                imported_node_ids.append(node_id)

        if not imported_node_ids:
            InfoBar.warning(
                "导入失败",
                project_manager.get_last_error_message() or "未能导入任何图片",
                parent=self._dialog_parent(),
                position=InfoBarPosition.TOP,
            )
            return

        self.refresh()
        self.select_node(imported_node_ids[-1])
        self.project_modified.emit()
        InfoBar.success(
            "导入完成",
            f"已导入 {len(imported_node_ids)} 张图片到数字化",
            parent=self._dialog_parent(),
            position=InfoBarPosition.TOP,
        )
        if failed_paths:
            InfoBar.warning(
                "部分导入失败",
                "以下图片未能导入: " + "、".join(failed_paths[:5]),
                parent=self._dialog_parent(),
                position=InfoBarPosition.TOP,
            )

    def _cmd_rename_virtual(self, kind: str, node_id: str, current_name: str) -> None:
        title = "重命名数据列" if kind == "series" else "重命名曲线"
        new_name, ok = TextInputDialog.get_text(self._dialog_parent(), title, "名称:", text=current_name)
        if not ok or not new_name.strip():
            return
        if kind == "series":
            changed = project_manager.rename_series(node_id, new_name.strip())
        else:
            changed = project_manager.rename_curve(node_id, new_name.strip())
        if changed:
            self.refresh()
            self.project_modified.emit()
            return
        InfoBar.warning(
            "重命名失败",
            project_manager.get_last_error_message() or "名称已存在或当前节点不支持重命名",
            parent=self._dialog_parent(),
            position=InfoBarPosition.TOP,
        )

    def _cmd_prune_empty_folders(self, root_id: Optional[str] = None, *, scope_label: str = "项目树") -> None:
        removed_ids = project_manager.remove_empty_folders(root_id)
        if not removed_ids:
            InfoBar.success(
                "无需清理",
                f"{scope_label} 中没有可移除的空文件夹",
                parent=self._dialog_parent(),
                position=InfoBarPosition.TOP,
            )
            return
        self.refresh()
        self.project_modified.emit()
        InfoBar.success(
            "清理完成",
            f"已移除 {len(removed_ids)} 个空文件夹",
            parent=self._dialog_parent(),
            position=InfoBarPosition.TOP,
        )

    def _cmd_delete_batch(self, payloads: List[Dict[str, object]]) -> None:
        count = len(payloads)
        names = [str(item["name"]) for item in payloads[:5]]
        summary = "\n".join(f"- {name}" for name in names)
        if count > 5:
            summary += f"\n- ... 另有 {count - 5} 项"
        box = MessageBox("确认批量删除", f"确定要删除选中的 {count} 项吗？\n\n{summary}", self._dialog_parent())
        if not box.exec():
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
            self.project_modified.emit()

    def _cmd_move_batch(self, payloads: List[Dict[str, object]], choices: List[Tuple[str, str]]) -> None:
        labels = [label for label, _ in choices]
        selected, ok = SelectionDialog.get_item(self._dialog_parent(), "批量移动到", "目标父级:", labels)
        if not ok or not selected:
            return
        target_id = next((target_id for label, target_id in choices if label == selected), None)
        if target_id is None:
            return

        changed = False
        failed = 0
        for payload in payloads:
            moved = self._move_node_to_target(str(payload["kind"]), str(payload["node_id"]), target_id)
            changed = moved or changed
            if not moved:
                failed += 1
        if changed:
            self.refresh()
            self.project_modified.emit()
        if failed:
            InfoBar.warning(
                "批量移动未完成",
                project_manager.get_last_error_message() or f"有 {failed} 项移动失败",
                parent=self._dialog_parent(),
                position=InfoBarPosition.TOP,
            )

    def _cmd_delete_virtual(self, kind: str, node_id: str, node_name: str) -> None:
        box = MessageBox("确认删除", f'确定要删除「{node_name}」吗？', self._dialog_parent())
        if not box.exec():
            return
        if kind == "series":
            changed = project_manager.delete_series(node_id)
        else:
            changed = project_manager.delete_curve(node_id)
        if changed:
            self.refresh()
            self.project_modified.emit()

    def _can_edit_global_asset(self, kind: str, node_id: str) -> bool:
        if kind == "global_report_template":
            item = global_assets.get_report_template(node_id)
            return bool(item is not None and not item.is_builtin)
        if kind == "global_curve_style_template":
            item = global_assets.get_curve_style_template(node_id)
            return bool(item is not None and not item.is_builtin)
        if kind in ("global_plot_style", "global_plot_theme"):
            style_type, asset_id = parse_plot_style_asset_key(node_id)
            if style_type == "template":
                return global_assets.get_figure_template(asset_id) is not None
            item = global_assets.get_plot_theme(asset_id)
            return bool(item is not None and not item.is_builtin)
        if kind == "global_extension_config":
            item = global_assets.get_extension_config(node_id)
            return bool(item is not None and not item.is_default)
        return kind in {
            "global_pipeline",
            "global_ai_prompt",
            "global_ai_skill",
            "global_ai_agent",
        }

    def _rename_global_asset(self, kind: str, node_id: str, new_name: str) -> bool:
        clean_name = new_name.strip()
        if not clean_name or not self._can_edit_global_asset(kind, node_id):
            return False
        if kind == "global_pipeline":
            return global_assets.update_saved_pipeline(node_id, name=clean_name)
        if kind == "global_report_template":
            return global_assets.update_report_template(node_id, name=clean_name)
        if kind == "global_curve_style_template":
            return global_assets.update_curve_style_template(node_id, name=clean_name)
        if kind in ("global_plot_style", "global_plot_theme"):
            style_type, asset_id = parse_plot_style_asset_key(node_id)
            if style_type == "template":
                return global_assets.update_figure_template(asset_id, name=clean_name)
            return global_assets.update_plot_theme(asset_id, name=clean_name)
        if kind == "global_extension_config":
            return global_assets.update_extension_config(node_id, name=clean_name) is not None
        if kind == "global_ai_prompt":
            return global_assets.update_ai_prompt(node_id, name=clean_name)
        if kind == "global_ai_skill":
            return global_assets.update_ai_skill(node_id, name=clean_name)
        if kind == "global_ai_agent":
            return global_assets.update_ai_agent(node_id, name=clean_name)
        return False

    def _delete_global_asset(self, kind: str, node_id: str) -> bool:
        if not self._can_edit_global_asset(kind, node_id):
            return False
        if kind == "global_pipeline":
            return global_assets.delete_saved_pipeline(node_id)
        if kind == "global_report_template":
            return global_assets.delete_report_template(node_id)
        if kind == "global_curve_style_template":
            return global_assets.delete_curve_style_template(node_id)
        if kind in ("global_plot_style", "global_plot_theme"):
            style_type, asset_id = parse_plot_style_asset_key(node_id)
            if style_type == "template":
                return global_assets.delete_figure_template(asset_id)
            return global_assets.delete_plot_theme(asset_id)
        if kind == "global_extension_config":
            return global_assets.delete_extension_config(node_id)
        if kind == "global_ai_prompt":
            return global_assets.delete_ai_prompt(node_id)
        if kind == "global_ai_skill":
            return global_assets.delete_ai_skill(node_id)
        if kind == "global_ai_agent":
            return global_assets.delete_ai_agent(node_id)
        return False

    def _cmd_rename_global(self, kind: str, node_id: str, current_name: str) -> None:
        title = "重命名全局资源"
        new_name, ok = TextInputDialog.get_text(self._dialog_parent(), title, "名称:", text=current_name)
        if not ok:
            return
        if self._rename_global_asset(kind, node_id, new_name):
            self.refresh()
            self.project_modified.emit()

    def _cmd_delete_global(self, kind: str, node_id: str, node_name: str) -> None:
        box = MessageBox("确认删除", f'确定要删除全局资源「{node_name}」吗？', self._dialog_parent())
        if not box.exec():
            return
        if self._delete_global_asset(kind, node_id):
            self.refresh()
            self.project_modified.emit()

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
        labels = [label for label, _ in choices]
        selected, ok = SelectionDialog.get_item(self._dialog_parent(), "移动到", "目标父级:", labels)
        if not ok or not selected:
            return
        target_id = next((target_id for label, target_id in choices if label == selected), None)
        if target_id and self._move_node_to_target(kind, node_id, target_id):
            self.refresh()
            self.project_modified.emit()
            return
        InfoBar.warning("移动失败", project_manager.get_last_error_message() or "目标位置已存在同名节点", parent=self, position=InfoBarPosition.TOP)

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
            if kind in {"project", *_SYNTHETIC_GLOBAL_KINDS}:
                return []

            project_id = item.data(0, _PROJECT_ROLE)
            if expected_kind is None:
                expected_kind = kind
            elif kind != expected_kind:
                return []

            if expected_project_id is None:
                expected_project_id = project_id
            elif project_id != expected_project_id:
                return []

            if kind == "folder" and self._is_protected_folder(project_manager.get_node_by_id(node_id)):
                return []

            ancestor = item.parent()
            while ancestor is not None:
                if self._item_key(ancestor) in selected_keys:
                    break
                ancestor = ancestor.parent()
            if ancestor is not None:
                continue

            payloads.append({
                "kind": kind,
                "node_id": node_id,
                "name": item.text(0),
            })

        return payloads if len(payloads) > 1 else []

    def _common_batch_move_choices(self, payloads: List[Dict[str, object]]) -> List[Tuple[str, str]]:
        if not payloads:
            return []

        first_kind = str(payloads[0]["kind"])
        choice_maps: List[Dict[str, str]] = []
        for payload in payloads:
            if str(payload["kind"]) != first_kind:
                return []
            current_choices = self._move_target_choices(first_kind, str(payload["node_id"]))
            if not current_choices:
                return []
            choice_maps.append({target_id: label for label, target_id in current_choices})

        common_ids = set(choice_maps[0])
        for choice_map in choice_maps[1:]:
            common_ids &= set(choice_map)
        if not common_ids:
            return []

        labels = choice_maps[0]
        return sorted([(labels[target_id], target_id) for target_id in common_ids], key=lambda item: item[0])

    # ─────────────────────────────────────────────────────────
    # 内部辅助
    # ─────────────────────────────────────────────────────────

    def _find_item(self, node_id: str) -> Optional[QTreeWidgetItem]:
        def _search(parent: Optional[QTreeWidgetItem]) -> Optional[QTreeWidgetItem]:
            count = (self._tree.topLevelItemCount() if parent is None
                     else parent.childCount())
            for i in range(count):
                item = (self._tree.topLevelItem(i) if parent is None
                        else parent.child(i))
                if item is None:
                    continue
                d = item.data(0, _ROLE)
                if d and d[1] == node_id:
                    return item
                found = _search(item)
                if found:
                    return found
            return None
        return _search(None)

    def _selected_items_or_current(self) -> List[QTreeWidgetItem]:
        items = [item for item in self._tree.selectedItems() if item is not None]
        if items:
            return items
        current = self._tree.currentItem()
        return [current] if current is not None else []

    def _item_key(self, item: Optional[QTreeWidgetItem]) -> Optional[str]:
        data = self._item_role_data(item)
        if not data:
            return None
        return f"{data[0]}:{data[1]}"

    def _item_role_data(self, item: Optional[QTreeWidgetItem]) -> Optional[Tuple[str, str]]:
        if item is None:
            return None
        try:
            data = item.data(0, _ROLE)
        except RuntimeError:
            return None
        if not data:
            return None
        return data

    def _item_project_id(self, item: Optional[QTreeWidgetItem]) -> Optional[str]:
        if item is None:
            return None
        try:
            return item.data(0, _PROJECT_ROLE)
        except RuntimeError:
            return None

    def _is_protected_folder(self, node) -> bool:
        if node is None or getattr(node, "kind", None) != "folder":
            return False
        group_type = self._canonical_group_type(getattr(node, "group_type", None))
        if group_type in _MANAGED_FOLDER_GROUP_TYPES:
            return getattr(node, "parent_id", None) is None
        return group_type in _PROTECTED_GROUP_TYPES

    def _dialog_parent(self) -> QWidget:
        window = self.window()
        return window if isinstance(window, QWidget) else self

    def _folder_icon(self, node, group_type: Optional[str]):
        if getattr(node, "parent_id", None) is not None:
            return FIF.FOLDER
        if group_type:
            return _GROUP_ICON.get(group_type, FIF.FOLDER)
        return FIF.FOLDER

    def _source_file_icon(self, node):
        source_file_id = getattr(node, "source_file_id", "")
        source_path = project_manager.get_source_file_path(source_file_id)
        if source_path and self._supports_source_file_digitize_import(source_path):
            return FIF.PHOTO
        return _SOURCE_FILE_ICON

    def _tooltip_item_at_event(self, event) -> Optional[QTreeWidgetItem]:
        if hasattr(event, "position"):
            return self._tree.itemAt(event.position().toPoint())
        if hasattr(event, "pos"):
            return self._tree.itemAt(event.pos())
        return None

    def _tooltip_global_pos(self, event) -> QPoint:
        if hasattr(event, "globalPos"):
            return event.globalPos()
        if hasattr(event, "position"):
            return self._tree.viewport().mapToGlobal(event.position().toPoint())
        if hasattr(event, "pos"):
            return self._tree.viewport().mapToGlobal(event.pos())
        return self._tree.viewport().mapToGlobal(self._tree.viewport().rect().center())

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

    def _append_tree_scope_actions(self, menu: RoundMenu, separated: bool = False) -> None:
        if separated and menu.actions():
            menu.addSeparator()
        self._add_menu_action(menu, FIF.SYNC, "清理空文件夹", self._cmd_prune_empty_folders)
        self._add_menu_action(menu, FIF.ZOOM_IN, "全部展开", self._expand_all_items)
        self._add_menu_action(menu, FIF.ZOOM_OUT, "全部折叠", self._collapse_all_items)

    def _expand_all_items(self) -> None:
        self._tree.expandAll()

    def _collapse_all_items(self) -> None:
        self._tree.collapseAll()

    def _add_menu_action(self, menu: RoundMenu, icon, text: str, callback) -> Action:
        action = Action(icon, text)
        action.triggered.connect(lambda checked=False: callback())
        menu.addAction(action)
        return action

    def _append_menu_section(self, menu: RoundMenu, entries: List[Tuple[object, str, object]]) -> None:
        visible_entries = [entry for entry in entries if entry is not None]
        if not visible_entries:
            return
        if menu.actions():
            menu.addSeparator()
        for icon, text, callback in visible_entries:
            self._add_menu_action(menu, icon, text, callback)

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

    def _lock_source_file_import_dialog_target(self, dialog, *, target_data_file_id: Optional[str]) -> None:
        combo = getattr(dialog, "_data_file_target_combo", None)
        keys = list(getattr(dialog, "_data_file_target_keys", []))
        if combo is None or not keys:
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

    def _apply_source_file_import_dialog_results(
        self,
        dialog,
        *,
        target_folder_id: Optional[str] = None,
        target_data_file_id: Optional[str] = None,
    ) -> Optional[str]:
        series_list = dialog.get_results()
        if not series_list:
            return None

        if target_data_file_id:
            data_file = project_manager.get_data_file(target_data_file_id)
            if data_file is None:
                InfoBar.warning(
                    "导入失败",
                    "所选目标数据文件不存在",
                    parent=self._dialog_parent(),
                    position=InfoBarPosition.TOP,
                )
                return None
            appended = 0
            for series in series_list:
                if project_manager.add_series_to_data_file(target_data_file_id, series):
                    appended += 1
            if appended != len(series_list):
                InfoBar.warning(
                    "导入失败",
                    project_manager.get_last_error_message() or "部分数据系列追加失败",
                    parent=self._dialog_parent(),
                    position=InfoBarPosition.TOP,
                )
                return None
            InfoBar.success(
                "导入成功",
                f"已导入 {len(series_list)} 条数据系列到数据文件 {data_file.name}",
                parent=self._dialog_parent(),
                position=InfoBarPosition.TOP,
            )
            return self._linked_tree_node_id("data_file", "data_file_id", target_data_file_id)

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
            InfoBar.warning(
                "导入失败",
                project_manager.get_last_error_message() or "未能创建新的数据文件",
                parent=self._dialog_parent(),
                position=InfoBarPosition.TOP,
            )
            return None
        InfoBar.success(
            "导入成功",
            f"已导入 {len(series_list)} 条数据系列到数据文件 {data_file.name}",
            parent=self._dialog_parent(),
            position=InfoBarPosition.TOP,
        )
        return node.id

    def _normalized_source_file_drop_target(self, target_item: Optional[QTreeWidgetItem]) -> Tuple[Optional[str], Optional[str]]:
        target_data = self._item_role_data(target_item)
        if not target_data:
            return None, None
        target_kind, target_id = target_data
        if target_kind == "series":
            parent_item = None if target_item is None else target_item.parent()
            parent_data = self._item_role_data(parent_item)
            if parent_data and parent_data[0] == "data_file":
                return parent_data
        return target_kind, target_id

    def _perform_source_file_drop_action(
        self,
        source_id: str,
        target_item: Optional[QTreeWidgetItem],
        *,
        defer_view_refresh: bool = False,
    ) -> bool:
        target_kind, target_id = self._normalized_source_file_drop_target(target_item)
        if not target_kind or not target_id:
            return False

        source_node = project_manager.get_node_by_id(source_id)
        if source_node is None or getattr(source_node, "kind", None) != "source_file":
            return False
        source_path = project_manager.get_source_file_path(getattr(source_node, "source_file_id", ""))
        source_asset = project_manager.get_source_file(getattr(source_node, "source_file_id", ""))
        if not source_path:
            return False

        target_data_file_id: Optional[str] = None
        target_folder_id: Optional[str] = None
        if target_kind == "data_file":
            target_node = project_manager.get_node_by_id(target_id)
            target_data_file_id = None if target_node is None else getattr(target_node, "data_file_id", None)
        elif target_kind == "folder":
            target_folder_id = target_id

        if target_data_file_id or (target_folder_id and self._folder_collection_group(target_folder_id) == "datasets"):
            if not self._supports_source_file_dataset_import(source_path):
                return False
            try:
                dialog = self._create_source_file_import_dialog(source_path)
            except Exception as exc:
                InfoBar.warning(
                    "导入失败",
                    f"无法读取文件: {exc}",
                    parent=self._dialog_parent(),
                    position=InfoBarPosition.TOP,
                )
                return False
            self._lock_source_file_import_dialog_target(dialog, target_data_file_id=target_data_file_id)
            if not dialog.exec():
                return False
            select_node_id = self._apply_source_file_import_dialog_results(
                dialog,
                target_folder_id=target_folder_id,
                target_data_file_id=target_data_file_id,
            )
            if not select_node_id:
                return False
            if defer_view_refresh:
                QTimer.singleShot(0, lambda node_id=select_node_id: self._finalize_drop_move(node_id))
            else:
                self._finalize_drop_move(select_node_id)
            self.project_modified.emit()
            return True

        if target_folder_id and self._folder_collection_group(target_folder_id) == "images":
            if not self._supports_source_file_digitize_import(source_path):
                return False
            try:
                image = project_manager.add_image(
                    source_path,
                    name=source_asset.name if source_asset is not None else Path(source_path).name,
                    parent_id=target_folder_id,
                )
            except ValueError as exc:
                InfoBar.warning("导入失败", str(exc), parent=self._dialog_parent(), position=InfoBarPosition.TOP)
                return False
            image_node_id = self._linked_tree_node_id("image_work", "image_work_id", image.id)
            select_node_id = image_node_id or target_folder_id
            InfoBar.success(
                "导入成功",
                f"已导入到数字化: {image.name}",
                parent=self._dialog_parent(),
                position=InfoBarPosition.TOP,
            )
            if defer_view_refresh:
                QTimer.singleShot(0, lambda node_id=select_node_id: self._finalize_drop_move(node_id))
            else:
                self._finalize_drop_move(select_node_id)
            self.project_modified.emit()
            return True

        return False

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

    def _resolve_drop_target_id(
        self,
        source_kind: str,
        source_id: str,
        target_item: Optional[QTreeWidgetItem],
    ) -> Optional[str]:
        target_data = self._item_role_data(target_item)
        if not target_data:
            return None
        target_kind, target_id = target_data
        resolved_target_id = self._resolve_virtual_drop_container_id(target_kind, target_id)
        if source_kind == "series":
            if target_kind == "data_file" and resolved_target_id != source_id:
                return resolved_target_id
            if target_kind == "series":
                parent_item = None if target_item is None else target_item.parent()
                parent_data = self._item_role_data(parent_item)
                if parent_data and parent_data[0] == "data_file":
                    return self._resolve_virtual_drop_container_id(parent_data[0], parent_data[1])
            return None
        if source_kind == "curve":
            if target_kind == "image_work" and resolved_target_id != source_id:
                return resolved_target_id
            if target_kind == "curve":
                parent_item = None if target_item is None else target_item.parent()
                parent_data = self._item_role_data(parent_item)
                if parent_data and parent_data[0] == "image_work":
                    return self._resolve_virtual_drop_container_id(parent_data[0], parent_data[1])
            return None
        if target_kind == "folder" and target_id != source_id:
            return target_id
        parent_item = None if target_item is None else target_item.parent()
        parent_data = self._item_role_data(parent_item)
        if parent_data and parent_data[0] == "folder":
            return parent_data[1]
        return None

    def _resolve_virtual_drop_container_id(self, target_kind: str, target_id: str) -> Optional[str]:
        if target_kind == "data_file":
            node = project_manager.get_node_by_id(target_id)
            return getattr(node, "data_file_id", None)
        if target_kind == "image_work":
            node = project_manager.get_node_by_id(target_id)
            return getattr(node, "image_work_id", None)
        return target_id

    def _perform_drop_move(
        self,
        source_item: Optional[QTreeWidgetItem],
        target_item: Optional[QTreeWidgetItem],
        defer_view_refresh: bool = False,
    ) -> bool:
        source_item = self._drag_source_item_for_drop(source_item)
        source_data = self._item_role_data(source_item)
        if not source_data:
            return False
        source_kind, source_id = source_data
        if source_kind in {"project", "global_root", "global_group"} or source_kind in _SYNTHETIC_GLOBAL_KINDS:
            return False
        source_project_id = self._item_project_id(source_item)
        target_project_id = self._item_project_id(target_item)
        if not source_project_id or source_project_id != target_project_id:
            return False
        project_manager.set_current_project(source_project_id)
        if source_kind == "source_file":
            return self._perform_source_file_drop_action(source_id, target_item, defer_view_refresh=defer_view_refresh)
        target_id = self._resolve_drop_target_id(source_kind, source_id, target_item)
        if not target_id or not self._move_node_to_target(source_kind, source_id, target_id):
            return False
        if defer_view_refresh:
            QTimer.singleShot(0, lambda node_id=source_id: self._finalize_drop_move(node_id))
        else:
            self._finalize_drop_move(source_id)
        self.project_modified.emit()
        return True

    def _finalize_drop_move(self, source_id: str) -> None:
        self.refresh()
        self.select_node(source_id)
        self._tree.viewport().update()
        self._tree.updateGeometry()

    def _remember_drag_source_item(self, item: Optional[QTreeWidgetItem]) -> None:
        self._drag_source_item_key = self._item_key(item)

    def _drag_source_item_for_drop(self, fallback_item: Optional[QTreeWidgetItem]) -> Optional[QTreeWidgetItem]:
        remembered = self._find_item_by_key(self._drag_source_item_key)
        return remembered or fallback_item

    def _clear_drag_source_item(self) -> None:
        self._drag_source_item_key = None

    def _folder_path_label(self, folder_id: str) -> str:
        return project_manager.format_tree_path_label(folder_id, separator="/", omit_root_group=True)

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

    @staticmethod
    def _expand_item_ancestors(item: Optional[QTreeWidgetItem]) -> None:
        current = item
        while current is not None:
            current.setExpanded(True)
            current = current.parent()

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
        self._tree.setWordWrap(wrap_mode)
        self._tree.setTextElideMode(Qt.TextElideMode.ElideNone if wrap_mode else Qt.TextElideMode.ElideRight)
        self._tree.setUniformRowHeights(not wrap_mode)
        if wrap_mode:
            self._update_wrapped_item_size_hints()
        else:
            self._reset_item_size_hints()
        self._tree.viewport().update()
        self._tree.updateGeometry()

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
