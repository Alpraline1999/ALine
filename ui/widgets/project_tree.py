"""
共享项目树组件 — ProjectTreeWidget

由 project_manager 数据驱动，可嵌入任意页面。
支持虚拟叶节点（DataSeries / Curve）、过滤模式、右键菜单、内联重命名。
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QInputDialog, QMenu, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    FluentIcon as FIF, MessageBox, TreeWidget,
)
from PySide6.QtWidgets import QTreeWidgetItem

from core.project_manager import project_manager


def _series_color_icon(color_str: str) -> QPixmap:
    """生成 16×16 纯色方块图标（用于 DataSeries / Curve 叶节点）。"""
    px = QPixmap(16, 16)
    px.fill(QColor(color_str if color_str else "#0078D4"))
    return px


# ── 每种 kind 的 (FluentIcon, 颜色hint) ──────────────────────────
_KIND_CONFIG = {
    "folder":          (FIF.FOLDER,          None),
    "data_file":       (FIF.DOCUMENT,        None),
    "image_work":      (FIF.PHOTO,           None),
    "pipeline":        (FIF.DEVELOPER_TOOLS, "#0078D4"),
    "figure_template": (FIF.PIE_SINGLE,      "#107C10"),
    "report_template": (FIF.DOCUMENT,        "#8C6C00"),
    "ai_tool":         (FIF.CHAT,            "#881798"),   # v0.2 compat
    "ai_prompt":       (FIF.CHAT,            "#881798"),
    "ai_skill":        (FIF.DEVELOPER_TOOLS, "#881798"),
    "ai_agent":        (FIF.ROBOT,           "#881798"),
}

# group_type → FluentIcon（系统文件夹专用图标）
_GROUP_ICON = {
    "datasets":       FIF.FOLDER,
    "dataset_set":    FIF.FOLDER,
    "images":         FIF.PHOTO,
    "image_set":      FIF.PHOTO,
    "tools":          FIF.DEVELOPER_TOOLS,
    "tool_set":       FIF.DEVELOPER_TOOLS,
    "pipeline_group": FIF.DEVELOPER_TOOLS,
    "template_group": FIF.PIE_SINGLE,
    "figure_template_group": FIF.PIE_SINGLE,
    "report_template_group": FIF.DOCUMENT,
    "ai_group":       FIF.ROBOT,
}

# 系统文件夹不可重命名/删除
_PROTECTED_GROUP_TYPES = frozenset({
    "datasets", "dataset_set",
    "images", "image_set",
    "tools", "tool_set",
    "pipeline_group", "template_group", "figure_template_group",
    "report_template_group", "ai_group",
})

_ROOT_GROUP_TYPES = frozenset({
    "datasets", "dataset_set",
    "images", "image_set",
    "tools", "tool_set",
})

# QTreeWidgetItem UserRole 存储 (kind, id)
_ROLE = Qt.ItemDataRole.UserRole


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

        self._tree = TreeWidget(self)
        self._tree.setHeaderHidden(True)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)

        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemActivated.connect(self._on_item_activated)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.itemChanged.connect(self._on_item_changed)

        layout.addWidget(self._tree)

        self._renaming = False  # 防止 itemChanged 循环

    # ─────────────────────────────────────────────────────────
    # 公开接口
    # ─────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """从 project_manager.current_project 完整重建树。"""
        self._tree.blockSignals(True)
        self._tree.clear()
        p = project_manager.current_project
        if p is None or p.tree is None:
            self._tree.blockSignals(False)
            return

        self._build_children(None, None)
        self._tree.blockSignals(False)

    def select_node(self, node_id: str) -> None:
        """程序化选中节点（不触发 node_selected 信号）。"""
        item = self._find_item(node_id)
        if item:
            self._tree.blockSignals(True)
            self._tree.setCurrentItem(item)
            self._tree.blockSignals(False)

    def set_filter_kinds(self, kinds: List[str]) -> None:
        """只显示指定 kind 的节点（空列表 = 显示全部）。"""
        self._filter_kinds = list(kinds)
        self.refresh()

    def get_selected_node(self) -> Optional[Tuple[str, str]]:
        """返回 (kind, node_id) 或 None。"""
        item = self._tree.currentItem()
        if item is None:
            return None
        d = item.data(0, _ROLE)
        if d:
            return d[0], d[1]
        return None

    # ─────────────────────────────────────────────────────────
    # 树构建
    # ─────────────────────────────────────────────────────────

    def _build_children(
        self, parent_id: Optional[str], parent_item: Optional[QTreeWidgetItem]
    ) -> None:
        p = project_manager.current_project
        if p is None or p.tree is None:
            return
        children = p.tree.get_children(parent_id)
        for node in children:
            kind = node.kind
            if self._filter_kinds and kind not in self._filter_kinds:
                if kind != "folder":
                    continue
            item = self._make_item(node)
            if parent_item is None:
                self._tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)

            # 递归子节点
            self._build_children(node.id, item)

            # 为 DataFileNode 追加虚拟 DataSeries 叶节点
            if kind == "data_file":
                if not self._filter_kinds or "series" in self._filter_kinds or "data_file" in self._filter_kinds:
                    df = p.find_data_file(node.data_file_id)
                    if df:
                        for series in df.series:
                            child = self._make_virtual_series_item(series)
                            item.addChild(child)

            # 为 ImageWorkNode 追加虚拟 Curve 叶节点
            elif kind == "image_work":
                if not self._filter_kinds or "curve" in self._filter_kinds or "image_work" in self._filter_kinds:
                    img = project_manager.get_image(node.image_work_id)
                    if img:
                        for curve in img.curves:
                            child = self._make_virtual_curve_item(curve)
                            item.addChild(child)

            # 过滤：文件夹下无可见子节点则隐藏
            is_root_folder = kind == "folder" and parent_id is None and getattr(node, "group_type", None) in _ROOT_GROUP_TYPES
            if kind == "folder" and self._filter_kinds and item.childCount() == 0 and not is_root_folder:
                if parent_item is None:
                    idx = self._tree.indexOfTopLevelItem(item)
                    self._tree.takeTopLevelItem(idx)
                else:
                    parent_item.removeChild(item)
                continue

            item.setExpanded(True)

    def _make_item(self, node) -> QTreeWidgetItem:
        item = QTreeWidgetItem([node.name])
        item.setData(0, _ROLE, (node.kind, node.id))

        # 系统文件夹不可内联编辑
        group_type = getattr(node, "group_type", None)
        is_protected = group_type in _PROTECTED_GROUP_TYPES
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if not is_protected:
            flags |= Qt.ItemFlag.ItemIsEditable
        item.setFlags(flags)

        # 图标选择
        if node.kind == "folder":
            icon_fif = _GROUP_ICON.get(group_type, FIF.FOLDER) if group_type else FIF.FOLDER
            item.setIcon(0, icon_fif.icon())
        else:
            cfg = _KIND_CONFIG.get(node.kind, (FIF.DOCUMENT, None))
            icon_fif, color_hint = cfg
            if icon_fif is not None:
                item.setIcon(0, icon_fif.icon())
            if color_hint:
                item.setForeground(0, QColor(color_hint))
        return item

    def _make_virtual_series_item(self, series) -> QTreeWidgetItem:
        """创建 DataSeries 虚拟叶节点（不存储在 project.tree 中）。"""
        item = QTreeWidgetItem([series.name or series.id[:8]])
        item.setData(0, _ROLE, ("series", series.id))
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item.setIcon(0, _series_color_icon(series.color or "#0078D4"))
        return item

    def _make_virtual_curve_item(self, curve) -> QTreeWidgetItem:
        """创建 Curve 虚拟叶节点。"""
        item = QTreeWidgetItem([curve.name or curve.id[:8]])
        item.setData(0, _ROLE, ("curve", curve.id))
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item.setIcon(0, FIF.PENCIL_INK.icon())
        item.setForeground(0, QColor(curve.color or "#0078D4"))
        return item

    # ─────────────────────────────────────────────────────────
    # 信号处理
    # ─────────────────────────────────────────────────────────

    def _on_item_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        d = item.data(0, _ROLE)
        if d:
            self.node_selected.emit(d[0], d[1])

    def _on_item_activated(self, item: QTreeWidgetItem, _col: int) -> None:
        d = item.data(0, _ROLE)
        if d:
            self.node_activated.emit(d[0], d[1])

    def _on_item_changed(self, item: QTreeWidgetItem, _col: int) -> None:
        if self._renaming:
            return
        d = item.data(0, _ROLE)
        if not d:
            return
        kind, node_id = d
        if kind in ("series", "curve"):
            return  # 虚拟节点，不可重命名
        new_name = item.text(0).strip()
        if not new_name:
            return
        self._renaming = True
        project_manager.rename_node(node_id, new_name)
        self._renaming = False
        self.project_modified.emit()

    # ─────────────────────────────────────────────────────────
    # 右键菜单
    # ─────────────────────────────────────────────────────────

    def _on_context_menu(self, pos) -> None:
        item = self._tree.itemAt(pos)
        menu = QMenu(self)

        if item is None:
            return

        d = item.data(0, _ROLE)
        if not d:
            return
        kind, node_id = d

        if kind == "folder":
            node = project_manager.get_node_by_id(node_id)
            group_type = getattr(node, "group_type", None) if node else None
            is_protected = group_type in _PROTECTED_GROUP_TYPES
            if not is_protected:
                menu.addAction(FIF.EDIT.icon(), "重命名").triggered.connect(
                    lambda: self._tree.editItem(item, 0))
                menu.addAction(FIF.DELETE.icon(), "删除").triggered.connect(
                    lambda: self._cmd_delete(node_id, item.text(0)))

        elif kind == "data_file":
            menu.addAction(FIF.PIE_SINGLE.icon(), "发送到可视化").triggered.connect(
                lambda: self.node_activated.emit("data_file_to_chart", node_id))
            menu.addAction(FIF.DEVELOPER_TOOLS.icon(), "发送到处理").triggered.connect(
                lambda: self.node_activated.emit("data_file_to_process", node_id))
            menu.addAction(FIF.SEARCH.icon(), "发送到分析").triggered.connect(
                lambda: self.node_activated.emit("data_file_to_analysis", node_id))
            menu.addSeparator()
            menu.addAction(FIF.EDIT.icon(), "重命名").triggered.connect(
                lambda: self._tree.editItem(item, 0))
            menu.addAction(FIF.DELETE.icon(), "删除").triggered.connect(
                lambda: self._cmd_delete(node_id, item.text(0)))

        elif kind == "series":
            menu.addAction(FIF.PIE_SINGLE.icon(), "发送到可视化").triggered.connect(
                lambda: self.node_activated.emit("series_to_chart", node_id))
            menu.addAction(FIF.DEVELOPER_TOOLS.icon(), "发送到处理").triggered.connect(
                lambda: self.node_activated.emit("series_to_process", node_id))
            menu.addAction(FIF.SEARCH.icon(), "发送到分析").triggered.connect(
                lambda: self.node_activated.emit("series_to_analysis", node_id))
            move_choices = self._move_target_choices(kind, node_id)
            menu.addSeparator()
            menu.addAction(FIF.EDIT.icon(), "重命名").triggered.connect(
                lambda: self._cmd_rename_virtual(kind, node_id, item.text(0)))
            menu.addAction(FIF.DELETE.icon(), "删除").triggered.connect(
                lambda: self._cmd_delete_virtual(kind, node_id, item.text(0)))
            if move_choices:
                menu.addAction(FIF.SWITCH.icon(), "移动到...").triggered.connect(
                    lambda: self._cmd_move_virtual(kind, node_id, move_choices))

        elif kind == "image_work":
            menu.addAction(FIF.EDIT.icon(), "打开取点").triggered.connect(
                lambda: self.node_activated.emit("image_work", node_id))
            menu.addAction(FIF.PIE_SINGLE.icon(), "发送到可视化").triggered.connect(
                lambda: self.node_activated.emit("image_work_to_chart", node_id))
            menu.addSeparator()
            menu.addAction(FIF.EDIT.icon(), "重命名").triggered.connect(
                lambda: self._tree.editItem(item, 0))
            menu.addAction(FIF.DELETE.icon(), "删除").triggered.connect(
                lambda: self._cmd_delete(node_id, item.text(0)))

        elif kind == "curve":
            menu.addAction(FIF.PIE_SINGLE.icon(), "发送到可视化").triggered.connect(
                lambda: self.node_activated.emit("curve_to_chart", node_id))
            menu.addAction(FIF.DEVELOPER_TOOLS.icon(), "发送到处理").triggered.connect(
                lambda: self.node_activated.emit("curve_to_process", node_id))
            menu.addAction(FIF.SEARCH.icon(), "发送到分析").triggered.connect(
                lambda: self.node_activated.emit("curve_to_analysis", node_id))
            move_choices = self._move_target_choices(kind, node_id)
            menu.addSeparator()
            menu.addAction(FIF.EDIT.icon(), "重命名").triggered.connect(
                lambda: self._cmd_rename_virtual(kind, node_id, item.text(0)))
            menu.addAction(FIF.DELETE.icon(), "删除").triggered.connect(
                lambda: self._cmd_delete_virtual(kind, node_id, item.text(0)))
            if move_choices:
                menu.addAction(FIF.SWITCH.icon(), "移动到...").triggered.connect(
                    lambda: self._cmd_move_virtual(kind, node_id, move_choices))

        elif kind == "pipeline":
            menu.addAction(FIF.DEVELOPER_TOOLS.icon(), "加载到处理页").triggered.connect(
                lambda: self.node_activated.emit("pipeline", node_id))
            menu.addSeparator()
            menu.addAction(FIF.EDIT.icon(), "重命名").triggered.connect(
                lambda: self._tree.editItem(item, 0))
            menu.addAction(FIF.DELETE.icon(), "删除").triggered.connect(
                lambda: self._cmd_delete(node_id, item.text(0)))

        elif kind == "figure_template":
            menu.addAction(FIF.PIE_SINGLE.icon(), "加载到可视化").triggered.connect(
                lambda: self.node_activated.emit("figure_template", node_id))
            menu.addSeparator()
            menu.addAction(FIF.EDIT.icon(), "重命名").triggered.connect(
                lambda: self._tree.editItem(item, 0))
            menu.addAction(FIF.DELETE.icon(), "删除").triggered.connect(
                lambda: self._cmd_delete(node_id, item.text(0)))

        elif kind == "report_template":
            menu.addAction(FIF.SEARCH.icon(), "加载到分析页").triggered.connect(
                lambda: self.node_activated.emit("report_template", node_id))
            menu.addSeparator()
            menu.addAction(FIF.EDIT.icon(), "重命名").triggered.connect(
                lambda: self._tree.editItem(item, 0))
            menu.addAction(FIF.DELETE.icon(), "删除").triggered.connect(
                lambda: self._cmd_delete(node_id, item.text(0)))

        elif kind in ("ai_prompt", "ai_skill", "ai_agent", "ai_tool"):
            menu.addAction(FIF.EDIT.icon(), "编辑").triggered.connect(
                lambda: self.node_activated.emit(kind, node_id))
            menu.addAction(FIF.DELETE.icon(), "删除").triggered.connect(
                lambda: self._cmd_delete(node_id, item.text(0)))

        if not menu.isEmpty():
            menu.exec(self._tree.viewport().mapToGlobal(pos))

    # ─────────────────────────────────────────────────────────
    # 命令
    # ─────────────────────────────────────────────────────────

    def _cmd_delete(self, node_id: str, node_name: str) -> None:
        box = MessageBox("确认删除", f'确定要删除「{node_name}」及其所有内容吗？', self)
        if box.exec():
            project_manager.delete_node(node_id)
            self.refresh()
            self.project_modified.emit()

    def _cmd_rename_virtual(self, kind: str, node_id: str, current_name: str) -> None:
        title = "重命名数据列" if kind == "series" else "重命名曲线"
        new_name, ok = QInputDialog.getText(self, title, "名称:", text=current_name)
        if not ok or not new_name.strip():
            return
        if kind == "series":
            changed = project_manager.rename_series(node_id, new_name.strip())
        else:
            changed = project_manager.rename_curve(node_id, new_name.strip())
        if changed:
            self.refresh()
            self.project_modified.emit()

    def _cmd_delete_virtual(self, kind: str, node_id: str, node_name: str) -> None:
        box = MessageBox("确认删除", f'确定要删除「{node_name}」吗？', self)
        if not box.exec():
            return
        if kind == "series":
            changed = project_manager.delete_series(node_id)
        else:
            changed = project_manager.delete_curve(node_id)
        if changed:
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
        selected, ok = QInputDialog.getItem(self, "移动到", "目标父级:", labels, 0, False)
        if not ok or not selected:
            return
        target_id = next((target_id for label, target_id in choices if label == selected), None)
        if target_id and self._move_node_to_target(kind, node_id, target_id):
            self.refresh()
            self.project_modified.emit()

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
                d = item.data(0, _ROLE)
                if d and d[1] == node_id:
                    return item
                found = _search(item)
                if found:
                    return found
            return None
        return _search(None)
