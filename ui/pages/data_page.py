"""数据管理页

三区域布局：左侧数据树 | 右上数据预览表格 | 右下统计摘要
支持从 PyLine 图像提取曲线复制为独立 DataSeries，以及文件导入。
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidgetItem, QAbstractItemView, QHeaderView,
    QFileDialog, QFrame, QSizePolicy,
)
from qfluentwidgets import (
    CardWidget, ToolButton, PushButton, PrimaryPushButton,
    TreeWidget, TableWidget, BodyLabel, CaptionLabel,
    FluentIcon as FIF, InfoBar, InfoBarPosition,
    MessageBox, MessageBoxBase, LineEdit,
)

from ui.theme import (
    text_color, secondary_color, card_background_color,
    make_section_label, make_hsep,
)
from core.project_manager import project_manager
from models.schemas import DataFile, DataSeries, Dataset, Curve


# ── 树节点类型常量 ────────────────────────────────────────────
_TYPE_ROOT    = "root"
_TYPE_IMAGE   = "image"
_TYPE_CURVE   = "curve"
_TYPE_DATASET = "dataset"
_TYPE_SERIES  = "series"
_TYPE_ANALYSIS_ROOT = "analysis_root"
_TYPE_ANALYSIS = "analysis"


class DataPage(QWidget):
    """数据管理页：统一管理图像提取曲线和导入数据集。"""

    send_to_visualize = Signal(str, str)   # (type: "curve"|"series", id)
    send_to_process   = Signal(str, str)   # (type, id)
    project_modified  = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_type: Optional[str] = None
        self._selected_id:   Optional[str] = None
        self._setup_ui()

    # ─────────────────────────────────────────────────────────
    # UI 构建
    # ─────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)
        root.addWidget(self._build_right_panel())

    # ── 左侧面板 ─────────────────────────────────────────────

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(240)
        panel.setMaximumWidth(360)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        lbl = make_section_label("共享树入口")
        toolbar.addWidget(lbl)
        toolbar.addStretch()

        self._btn_add_ds = ToolButton(FIF.ADD)
        self._btn_add_ds.setToolTip("新建数据集")
        self._btn_add_ds.clicked.connect(self._add_dataset)
        self._btn_import = ToolButton(FIF.DOWNLOAD)
        self._btn_import.setToolTip("导入文件")
        self._btn_import.clicked.connect(self._import_file)
        toolbar.addWidget(self._btn_add_ds)
        toolbar.addWidget(self._btn_import)
        layout.addLayout(toolbar)

        self._shared_tree_hint = CaptionLabel("请使用左侧共享项目树选择数据资产；此处仅保留当前对象相关操作。", panel)
        self._shared_tree_hint.setWordWrap(True)
        layout.addWidget(self._shared_tree_hint)

        # 树
        self._tree = TreeWidget(self)
        self._tree.setHeaderHidden(True)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        self._tree.hide()
        layout.addWidget(self._tree)

        # 底部操作按钮
        layout.addWidget(make_hsep())
        btn_row = QHBoxLayout()
        self._btn_copy_curve = PushButton("曲线→数据集")
        self._btn_copy_curve.setToolTip("将选中的图像提取曲线复制为独立数据系列")
        self._btn_copy_curve.clicked.connect(self._copy_curve_to_series)
        self._btn_delete = ToolButton(FIF.DELETE)
        self._btn_delete.setToolTip("删除选中项")
        self._btn_delete.clicked.connect(self._delete_selected)
        btn_row.addWidget(self._btn_copy_curve)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_delete)
        layout.addLayout(btn_row)

        return panel

    # ── 右侧面板 ─────────────────────────────────────────────

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._shared_tree_hint = CaptionLabel("请使用左侧共享项目树选择数据资产。", panel)
        self._shared_tree_hint.setWordWrap(True)
        layout.addWidget(self._shared_tree_hint)

        layout.addWidget(make_hsep())

        # 数据预览表格
        layout.addWidget(make_section_label("数据预览"))
        self._table = TableWidget(self)
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(["X", "Y"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table, stretch=3)

        layout.addWidget(make_hsep())

        # 统计摘要
        layout.addWidget(make_section_label("统计摘要"))
        self._stats_label = BodyLabel("（选择数据后显示统计信息）")
        self._stats_label.setWordWrap(True)
        layout.addWidget(self._stats_label)

        layout.addWidget(make_hsep())

        # 发送按钮
        action_row = QHBoxLayout()
        self._btn_to_vis  = PrimaryPushButton(FIF.PIE_SINGLE, "→ 可视化")
        self._btn_to_proc = PushButton(FIF.DEVELOPER_TOOLS, "→ 处理")
        self._btn_export  = PushButton(FIF.SHARE, "导出 CSV")
        self._btn_to_vis.clicked.connect(self._send_to_visualize)
        self._btn_to_proc.clicked.connect(self._send_to_process)
        self._btn_export.clicked.connect(self._export_csv)
        action_row.addWidget(self._btn_to_vis)
        action_row.addWidget(self._btn_to_proc)
        action_row.addStretch()
        action_row.addWidget(self._btn_export)
        layout.addLayout(action_row)

        self._set_actions_enabled(False)
        return panel

    # ─────────────────────────────────────────────────────────
    # 树刷新
    # ─────────────────────────────────────────────────────────

    def refresh(self):
        """刷新页面状态。"""
        self._clear_preview()
        p = project_manager.current_project
        if p is None:
            self._shared_tree_hint.setText("请先打开项目，然后通过左侧共享项目树选择数据资产。")
        else:
            self._shared_tree_hint.setText("请使用左侧共享项目树选择数据资产。")

    def _clear_preview(self):
        self._table.setRowCount(0)
        self._stats_label.setText("（选择数据后显示统计信息）")
        self._set_actions_enabled(False)

    # ─────────────────────────────────────────────────────────
    # 选中事件 → 更新预览
    # ─────────────────────────────────────────────────────────

    def _on_selection_changed(self):
        items = self._tree.selectedItems()
        if not items:
            self._clear_preview()
            return

        item = items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            self._clear_preview()
            return

        typ, obj_id = data
        self._selected_type = typ
        self._selected_id   = obj_id

        p = project_manager.current_project
        if p is None:
            return

        if typ == _TYPE_CURVE:
            curve = p.find_curve_by_id(obj_id) if hasattr(p, 'find_curve_by_id') else self._find_curve(p, obj_id)
            if curve:
                self._show_xy_preview(curve.x_actual, curve.y_actual, curve.name)
        elif typ == _TYPE_SERIES:
            series = p.find_series(obj_id)
            if series:
                self._show_xy_preview(series.x, series.y, series.name)
        else:
            self._clear_preview()
            return

        self._set_actions_enabled(typ in (_TYPE_CURVE, _TYPE_SERIES))

    def _find_curve(self, project, curve_id: str) -> Optional[Curve]:
        for img in project.images:
            for c in img.curves:
                if c.id == curve_id:
                    return c
        for c in project.imported_curves:
            if c.id == curve_id:
                return c
        return None

    def _show_xy_preview(self, xs, ys, name: str):
        """填充预览表格和统计摘要。"""
        n = min(len(xs), len(ys))
        self._table.setRowCount(n)

        x_lbl = "X"
        y_lbl = "Y"
        self._table.setHorizontalHeaderLabels([x_lbl, y_lbl])

        from PySide6.QtWidgets import QTableWidgetItem
        for i in range(n):
            self._table.setItem(i, 0, QTableWidgetItem(f"{xs[i]:.6g}"))
            self._table.setItem(i, 1, QTableWidgetItem(f"{ys[i]:.6g}"))

        # 统计
        if n > 0:
            x_min, x_max = min(xs[:n]), max(xs[:n])
            y_min, y_max = min(ys[:n]), max(ys[:n])
            y_mean = sum(ys[:n]) / n
            y_var  = sum((v - y_mean)**2 for v in ys[:n]) / n
            y_std  = math.sqrt(y_var)
            self._stats_label.setText(
                f"N = {n}    X: [{x_min:.4g}, {x_max:.4g}]    Y: [{y_min:.4g}, {y_max:.4g}]\n"
                f"均值 = {y_mean:.4g}    标准差 = {y_std:.4g}"
            )

    def _set_actions_enabled(self, enabled: bool):
        self._btn_to_vis.setEnabled(enabled)
        self._btn_to_proc.setEnabled(enabled)
        self._btn_export.setEnabled(enabled)

    # ─────────────────────────────────────────────────────────
    # 操作：导入文件
    # ─────────────────────────────────────────────────────────

    def _import_file(self):
        p = project_manager.current_project
        if p is None:
            InfoBar.warning("提示", "请先打开项目", parent=self, position=InfoBarPosition.TOP)
            return

        from ui.dialogs.import_dialog import ImportDialog
        dlg = ImportDialog(self)
        if dlg.exec():
            series_list = dlg.get_results()
            if not series_list:
                return
            df = DataFile(name=dlg.get_file_name(), series=series_list)
            project_manager.add_data_file(df)
            self.refresh()
            self.project_modified.emit()
            InfoBar.success("导入成功", f"已导入 {len(series_list)} 条数据系列到数据文件 {df.name}", parent=self, position=InfoBarPosition.TOP)

    # ─────────────────────────────────────────────────────────
    # 操作：新建数据集
    # ─────────────────────────────────────────────────────────

    def _add_dataset(self):
        p = project_manager.current_project
        if p is None:
            return
        from qfluentwidgets import MessageBoxBase, SubtitleLabel
        dlg = _NameDialog("新建数据集", "数据集名称:", "新数据集", self)
        if dlg.exec():
            name = dlg.get_name()
            if name:
                project_manager.add_dataset(name)
                self.refresh()
                self.project_modified.emit()

    # ─────────────────────────────────────────────────────────
    # 操作：曲线 → DataSeries
    # ─────────────────────────────────────────────────────────

    def _copy_curve_to_series(self):
        if self._selected_type != _TYPE_CURVE or not self._selected_id:
            InfoBar.info("提示", "请在树中选中一条图像提取曲线", parent=self, position=InfoBarPosition.TOP)
            return
        p = project_manager.current_project
        if p is None:
            return
        # 确保有目标数据集
        if not p.datasets:
            project_manager.add_dataset("提取曲线")
        target_ds = p.datasets[-1]
        result = project_manager.import_curve_as_series(self._selected_id, target_ds.id)
        if result:
            self.refresh()
            self.project_modified.emit()
            InfoBar.success("已复制", f"'{result.name}' 已加入数据集 '{target_ds.name}'", parent=self, position=InfoBarPosition.TOP)

    # ─────────────────────────────────────────────────────────
    # 操作：删除
    # ─────────────────────────────────────────────────────────

    def _delete_selected(self):
        if not self._selected_id or not self._selected_type:
            return
        p = project_manager.current_project
        if p is None:
            return

        if self._selected_type == _TYPE_DATASET:
            ds = p.find_dataset(self._selected_id)
            name = ds.name if ds else ""
            dlg = MessageBox("删除数据集", f"确定删除数据集 '{name}' 及其所有数据系列？", self)
            if dlg.exec():
                project_manager.remove_dataset(self._selected_id)
                self.refresh()
                self.project_modified.emit()

        elif self._selected_type == _TYPE_SERIES:
            for ds in (p.datasets or []):
                for s in ds.series:
                    if s.id == self._selected_id:
                        dlg = MessageBox("删除数据系列", f"确定删除 '{s.name}'？", self)
                        if dlg.exec():
                            project_manager.remove_series(ds.id, self._selected_id)
                            self.refresh()
                            self.project_modified.emit()
                        return

        elif self._selected_type == _TYPE_ANALYSIS:
            dlg = MessageBox("删除分析结果", "确定删除该分析结果？", self)
            if dlg.exec():
                project_manager.remove_analysis(self._selected_id)
                self.refresh()
                self.project_modified.emit()

    # ─────────────────────────────────────────────────────────
    # 操作：右键菜单
    # ─────────────────────────────────────────────────────────

    def _show_context_menu(self, pos):
        item = self._tree.itemAt(pos)
        if item is None:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        typ, obj_id = data

        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        if typ == _TYPE_CURVE:
            menu.addAction("复制为 DataSeries").triggered.connect(self._copy_curve_to_series)
            menu.addAction("→ 可视化").triggered.connect(self._send_to_visualize)
        elif typ == _TYPE_DATASET:
            menu.addAction("重命名").triggered.connect(lambda: self._rename_dataset(obj_id))
            menu.addAction("删除").triggered.connect(self._delete_selected)
        elif typ == _TYPE_SERIES:
            menu.addAction("→ 可视化").triggered.connect(self._send_to_visualize)
            menu.addAction("→ 处理").triggered.connect(self._send_to_process)
            menu.addAction("导出 CSV").triggered.connect(self._export_csv)
            menu.addSeparator()
            menu.addAction("删除").triggered.connect(self._delete_selected)
        elif typ == _TYPE_ANALYSIS:
            menu.addAction("删除").triggered.connect(self._delete_selected)

        if menu.actions():
            menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _rename_dataset(self, ds_id: str):
        p = project_manager.current_project
        if p is None:
            return
        ds = p.find_dataset(ds_id)
        if ds is None:
            return
        dlg = _NameDialog("重命名数据集", "新名称:", ds.name, self)
        if dlg.exec():
            new_name = dlg.get_name()
            if new_name:
                project_manager.rename_dataset(ds_id, new_name)
                self.refresh()
                self.project_modified.emit()

    # ─────────────────────────────────────────────────────────
    # 操作：发送 / 导出
    # ─────────────────────────────────────────────────────────

    def _send_to_visualize(self):
        if self._selected_type and self._selected_id:
            self.send_to_visualize.emit(self._selected_type, self._selected_id)

    def _send_to_process(self):
        if self._selected_type and self._selected_id:
            self.send_to_process.emit(self._selected_type, self._selected_id)

    def _export_csv(self):
        if not self._selected_id or not self._selected_type:
            return
        p = project_manager.current_project
        xs, ys, name = [], [], "data"
        if self._selected_type == _TYPE_CURVE:
            c = self._find_curve(p, self._selected_id)
            if c:
                xs, ys, name = c.x_actual, c.y_actual, c.name
        elif self._selected_type == _TYPE_SERIES:
            s = p.find_series(self._selected_id)
            if s:
                xs, ys, name = s.x, s.y, s.name
        if not xs:
            return

        path, _ = QFileDialog.getSaveFileName(self, "导出 CSV", f"{name}.csv", "CSV 文件 (*.csv)")
        if not path:
            return
        import csv
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["x", "y"])
            for x, y in zip(xs, ys):
                w.writerow([x, y])
        InfoBar.success("导出成功", path, parent=self, position=InfoBarPosition.TOP)

    # ─────────────────────────────────────────────────────────
    # 主题更新
    # ─────────────────────────────────────────────────────────

    def update_theme(self):
        pass

    def on_tree_node_selected(self, kind: str, node_id: str) -> None:
        """共享树选中节点 → 显示预览。"""
        self._shared_tree_hint.setText(f"当前共享树节点: {kind} / {node_id}")
        if kind in ("data_file", "series", "curve", "image_work"):
            series = project_manager.get_series_from_node(kind, node_id)
            if series and series.x:
                self._selected_type = "series" if kind in ("data_file", "series") else "curve"
                self._selected_id = series.id
                self._show_xy_preview(series.x, series.y, series.name)
                self._set_actions_enabled(True)
                return
        self._selected_type = None
        self._selected_id = None
        self._clear_preview()


# ── 辅助对话框 ────────────────────────────────────────────────

class _NameDialog(MessageBoxBase):
    def __init__(self, title: str, label: str, default: str = "", parent=None):
        super().__init__(parent)
        from qfluentwidgets import SubtitleLabel
        self.viewLayout.addWidget(SubtitleLabel(title))
        self.viewLayout.addWidget(BodyLabel(label))
        self._edit = LineEdit()
        self._edit.setText(default)
        self._edit.selectAll()
        self.viewLayout.addWidget(self._edit)
        self.yesButton.setText("确认")
        self.cancelButton.setText("取消")

    def get_name(self) -> str:
        return self._edit.text().strip()
