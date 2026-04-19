"""数据管理页

三区域布局：左侧数据树 | 右上数据预览表格 | 右下统计摘要
支持从 PyLine 图像提取曲线复制为独立 DataSeries，以及文件导入。
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidgetItem, QAbstractItemView,
    QFileDialog, QFrame, QLabel, QSizePolicy, QStackedWidget,
)
from qfluentwidgets import (
    ComboBox,
    CardWidget, ToolButton, PushButton, PrimaryPushButton,
    TreeWidget, BodyLabel, CaptionLabel, PlainTextEdit,
    FluentIcon as FIF, InfoBar, InfoBarPosition,
    MessageBox, MessageBoxBase, LineEdit,
)

from ui.theme import (
    text_color, secondary_color, card_background_color,
    make_section_label, make_hsep,
)
from ui.matplotlib_fonts import configure_matplotlib_cjk
from core.project_manager import project_manager
from models.schemas import DataFile, DataSeries, Dataset, Curve

try:
    import matplotlib

    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    configure_matplotlib_cjk(matplotlib)
    HAS_MATPLOTLIB = True
    _MATPLOTLIB_ERROR = ""
except Exception as exc:
    HAS_MATPLOTLIB = False
    _MATPLOTLIB_ERROR = f"{type(exc).__name__}: {exc}"


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
    tree_filter_kinds = ["folder", "data_file", "image_work", "series", "curve", "analysis_result"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_type: Optional[str] = None
        self._selected_id:   Optional[str] = None
        self._selected_node_kind: Optional[str] = None
        self._selected_node_id: Optional[str] = None
        self._preview_xs: list[float] = []
        self._preview_ys: list[float] = []
        self._preview_name = ""
        self._preview_x_label = "X"
        self._preview_y_label = "Y"
        self._setup_ui()

    # ─────────────────────────────────────────────────────────
    # UI 构建
    # ─────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
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

        preview_card = CardWidget(panel)
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(14, 14, 14, 14)
        preview_layout.setSpacing(10)

        preview_header = QHBoxLayout()
        preview_header.addWidget(make_section_label("数据预览"))
        preview_header.addStretch()
        preview_header.addWidget(CaptionLabel("图型", preview_card))
        self._preview_type_combo = ComboBox(preview_card)
        self._preview_type_combo.addItems(["折线", "散点", "折线+点", "柱状", "阶梯"])
        self._preview_type_combo.currentIndexChanged.connect(self._draw_preview)
        preview_header.addWidget(self._preview_type_combo)
        preview_layout.addLayout(preview_header)

        self._preview_stack = QStackedWidget(preview_card)
        preview_layout.addWidget(self._preview_stack, stretch=3)

        self._plot_preview_panel = QWidget(preview_card)
        plot_preview_layout = QVBoxLayout(self._plot_preview_panel)
        plot_preview_layout.setContentsMargins(0, 0, 0, 0)
        plot_preview_layout.setSpacing(0)

        if HAS_MATPLOTLIB:
            self._preview_figure = Figure(figsize=(5.6, 3.4), dpi=100)
            self._preview_canvas = FigureCanvas(self._preview_figure)
            plot_preview_layout.addWidget(self._preview_canvas, stretch=1)
        else:
            self._preview_figure = None
            self._preview_canvas = None
            self._preview_canvas_label = BodyLabel(
                f"matplotlib 加载失败：{_MATPLOTLIB_ERROR}" if _MATPLOTLIB_ERROR else "请安装 matplotlib 以启用绘图预览",
                preview_card,
            )
            self._preview_canvas_label.setWordWrap(True)
            self._preview_canvas_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            plot_preview_layout.addWidget(self._preview_canvas_label, stretch=1)

        self._preview_stack.addWidget(self._plot_preview_panel)

        self._image_preview_label = QLabel(preview_card)
        self._image_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_preview_label.setMinimumHeight(240)
        self._image_preview_label.setWordWrap(True)
        self._preview_stack.addWidget(self._image_preview_label)

        self._text_preview = PlainTextEdit(preview_card)
        self._text_preview.setReadOnly(True)
        self._text_preview.setMinimumHeight(240)
        self._preview_stack.addWidget(self._text_preview)

        preview_layout.addWidget(make_hsep())

        preview_layout.addWidget(make_section_label("统计摘要"))
        self._stats_label = BodyLabel("（选择数据后显示统计信息）")
        self._stats_label.setWordWrap(True)
        self._stats_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        preview_layout.addWidget(self._stats_label)

        layout.addWidget(preview_card, stretch=3)

        manage_card = CardWidget(panel)
        manage_layout = QVBoxLayout(manage_card)
        manage_layout.setContentsMargins(14, 14, 14, 14)
        manage_layout.setSpacing(10)

        manage_layout.addWidget(make_section_label("节点管理"))
        self._shared_tree_hint = CaptionLabel("从左侧共享项目树选择数据节点后，可在这里直接重命名、复制或删除。", manage_card)
        self._shared_tree_hint.setWordWrap(True)
        manage_layout.addWidget(self._shared_tree_hint)

        self._manage_target_label = BodyLabel("当前节点: 未选择")
        self._manage_target_label.setWordWrap(True)
        self._manage_target_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        manage_layout.addWidget(self._manage_target_label)

        self._manage_type_label = CaptionLabel("节点类型: -", manage_card)
        self._manage_type_label.setWordWrap(True)
        manage_layout.addWidget(self._manage_type_label)

        name_row = QHBoxLayout()
        name_row.addWidget(BodyLabel("名称:"))
        self._manage_name_edit = LineEdit(manage_card)
        self._manage_name_edit.setPlaceholderText("选择节点后可编辑名称")
        name_row.addWidget(self._manage_name_edit, 1)
        self._btn_apply_name = PushButton("应用重命名", manage_card)
        self._btn_apply_name.clicked.connect(self._apply_rename_current_node)
        name_row.addWidget(self._btn_apply_name)
        manage_layout.addLayout(name_row)

        manage_layout.addWidget(make_hsep())

        primary_row = QHBoxLayout()
        self._btn_copy_to_data_file = PushButton("复制为数据文件", manage_card)
        self._btn_copy_to_data_file.clicked.connect(self._duplicate_current_node_as_data_file)
        primary_row.addWidget(self._btn_copy_to_data_file)
        self._btn_delete_node = PushButton("删除当前节点", manage_card)
        self._btn_delete_node.clicked.connect(self._delete_current_node)
        primary_row.addWidget(self._btn_delete_node)
        primary_row.addStretch()
        manage_layout.addLayout(primary_row)

        action_row = QHBoxLayout()
        self._btn_to_vis = PrimaryPushButton(FIF.PIE_SINGLE, "→ 可视化")
        self._btn_to_proc = PushButton(FIF.DEVELOPER_TOOLS, "→ 处理")
        self._btn_export = PushButton(FIF.SHARE, "导出 CSV")
        self._btn_to_vis.clicked.connect(self._send_to_visualize)
        self._btn_to_proc.clicked.connect(self._send_to_process)
        self._btn_export.clicked.connect(self._export_csv)
        action_row.addWidget(self._btn_to_vis)
        action_row.addWidget(self._btn_to_proc)
        action_row.addStretch()
        action_row.addWidget(self._btn_export)
        manage_layout.addLayout(action_row)

        self._manage_help_label = CaptionLabel("数据文件、系列和曲线支持直接复制为新的数据文件；图像节点支持重命名和删除。", manage_card)
        self._manage_help_label.setWordWrap(True)
        manage_layout.addWidget(self._manage_help_label)

        layout.addWidget(manage_card, stretch=2)

        self._set_actions_enabled(False)
        self._set_management_actions_enabled(False)
        return panel

    # ─────────────────────────────────────────────────────────
    # 树刷新
    # ─────────────────────────────────────────────────────────

    def refresh(self):
        """刷新页面状态。"""
        self._clear_preview()
        p = project_manager.current_project
        if p is None:
            self._selected_node_kind = None
            self._selected_node_id = None
            self._shared_tree_hint.setText("请先打开项目，然后通过左侧共享项目树选择数据资产。")
        else:
            n_files = len(p.data_files)
            n_series = sum(len(df.series) for df in p.data_files)
            n_curves = sum(len(img.curves) for img in p.images)
            self._shared_tree_hint.setText(
                f"数据文件 {n_files} 个 · 系列 {n_series} 条 · 图像曲线 {n_curves} 条　│　"
                "请从左侧共享项目树选择数据资产"
            )
        self._refresh_management_panel()

    def _clear_preview(self):
        self._preview_xs = []
        self._preview_ys = []
        self._preview_name = ""
        self._preview_x_label = "X"
        self._preview_y_label = "Y"
        self._preview_stack.setCurrentWidget(self._plot_preview_panel)
        self._draw_preview()
        self._text_preview.clear()
        self._image_preview_label.clear()
        self._image_preview_label.setText("选择节点后显示预览")
        self._stats_label.setText("（选择数据后显示统计信息）")
        self._set_actions_enabled(False)

    def _set_management_actions_enabled(self, enabled: bool, *, allow_copy: bool = False) -> None:
        self._manage_name_edit.setEnabled(enabled)
        self._btn_apply_name.setEnabled(enabled)
        self._btn_delete_node.setEnabled(enabled)
        self._btn_copy_to_data_file.setEnabled(enabled and allow_copy)

    def _current_tree_node(self):
        project = project_manager.current_project
        if project is None or project.tree is None or not self._selected_node_id:
            return None
        return project.tree.get_node(self._selected_node_id)

    def _current_node_name(self) -> str:
        project = project_manager.current_project
        if project is None or not self._selected_node_kind or not self._selected_node_id:
            return ""
        if self._selected_node_kind == "series":
            series = project.find_series(self._selected_node_id)
            return "" if series is None else series.name
        if self._selected_node_kind == "curve":
            curve = self._find_curve(project, self._selected_node_id)
            return "" if curve is None else curve.name
        if self._selected_node_kind == "image_work":
            node = self._current_tree_node()
            if node is None:
                return ""
            image = project_manager.get_image(node.image_work_id)
            return image.name if image is not None else node.name
        node = self._current_tree_node()
        return "" if node is None else node.name

    @staticmethod
    def _canonical_folder_group(group_type: Optional[str]) -> Optional[str]:
        if group_type in {"dataset_set", "datasets"}:
            return "datasets"
        if group_type in {"image_set", "images"}:
            return "images"
        if group_type in {"tool_set", "tools"}:
            return "tools"
        if group_type in {"template_group", "figure_template_group"}:
            return "figure_template_group"
        return group_type

    def _folder_collection_group(self, node) -> Optional[str]:
        current = node
        while current is not None and getattr(current, "kind", None) == "folder":
            group_type = self._canonical_folder_group(getattr(current, "group_type", None))
            if group_type in {"datasets", "images", "analysis_result_group"}:
                return group_type
            parent_id = getattr(current, "parent_id", None)
            current = project_manager.get_node_by_id(parent_id) if parent_id else None
        return None

    def _is_protected_folder_node(self, node) -> bool:
        if node is None or getattr(node, "kind", None) != "folder":
            return False
        group_type = self._canonical_folder_group(getattr(node, "group_type", None))
        if group_type in {"datasets", "images", "analysis_result_group"}:
            return getattr(node, "parent_id", None) is None
        return group_type in {
            "tools", "pipeline_group", "figure_template_group",
            "report_template_group", "ai_group", "prompt_group",
            "skill_group", "agent_group",
        }

    def _current_data_file_node(self):
        project = project_manager.current_project
        if project is None or project.tree is None or not self._selected_node_kind or not self._selected_node_id:
            return None
        if self._selected_node_kind == "data_file":
            node = self._current_tree_node()
            return node if node is not None and getattr(node, "kind", None) == "data_file" else None
        if self._selected_node_kind != "series":
            return None
        for node in project.tree.nodes:
            if node.kind != "data_file":
                continue
            data_file = project.find_data_file(node.data_file_id)
            if data_file and any(series.id == self._selected_node_id for series in data_file.series):
                return node
        return None

    def _current_dataset_parent_id(self) -> Optional[str]:
        project = project_manager.current_project
        if project is None or project.tree is None:
            return None
        if self._selected_node_kind == "folder":
            node = self._current_tree_node()
            if self._folder_collection_group(node) == "datasets":
                return getattr(node, "id", None)
            return None
        data_file_node = self._current_data_file_node()
        if data_file_node is None or not getattr(data_file_node, "parent_id", None):
            return None
        parent = project.tree.get_node(data_file_node.parent_id)
        if self._folder_collection_group(parent) == "datasets":
            return parent.id
        return None

    @staticmethod
    def _node_kind_label(kind: Optional[str]) -> str:
        mapping = {
            "folder": "文件夹",
            "data_file": "数据文件",
            "series": "数据系列",
            "image_work": "图像",
            "curve": "图像曲线",
            "analysis_result": "分析结果",
        }
        return mapping.get(kind or "", "-")

    def _can_rename_current_node(self) -> bool:
        if not self._selected_node_kind or not self._selected_node_id:
            return False
        if self._selected_node_kind in {"data_file", "series", "curve", "image_work"}:
            return True
        if self._selected_node_kind == "folder":
            return not self._is_protected_folder_node(self._current_tree_node())
        return False

    def _can_delete_current_node(self) -> bool:
        if not self._selected_node_kind or not self._selected_node_id:
            return False
        if self._selected_node_kind in {"data_file", "series", "curve", "image_work"}:
            return True
        if self._selected_node_kind == "folder":
            return not self._is_protected_folder_node(self._current_tree_node())
        return False

    def _refresh_management_panel(self) -> None:
        if not self._selected_node_kind or not self._selected_node_id:
            self._manage_target_label.setText("当前节点: 未选择")
            self._manage_type_label.setText("节点类型: -")
            self._manage_name_edit.clear()
            self._set_management_actions_enabled(False)
            return

        current_name = self._current_node_name() or "未命名节点"
        self._manage_target_label.setText(f"当前节点: {current_name}")
        self._manage_type_label.setText(f"节点类型: {self._node_kind_label(self._selected_node_kind)}")
        self._manage_name_edit.setText(current_name)
        allow_copy = self._selected_node_kind in {"data_file", "series", "curve"}
        enabled = self._can_rename_current_node() or self._can_delete_current_node()
        self._manage_name_edit.setEnabled(self._can_rename_current_node())
        self._btn_apply_name.setEnabled(self._can_rename_current_node())
        self._btn_delete_node.setEnabled(self._can_delete_current_node())
        self._btn_copy_to_data_file.setEnabled(allow_copy)
        if not enabled and not allow_copy:
            self._manage_help_label.setText("当前节点仅支持预览，不支持直接管理操作。")
        else:
            self._manage_help_label.setText("数据文件、系列和曲线支持直接复制为新的数据文件；图像节点支持重命名和删除。")

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
                self._show_xy_preview(series.x, series.y, series.name, series.x_label, series.y_label)
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

    @staticmethod
    def _preview_bar_width(xs: list[float]) -> float:
        if len(xs) < 2:
            return 0.8
        diffs = [abs(xs[idx + 1] - xs[idx]) for idx in range(len(xs) - 1) if xs[idx + 1] != xs[idx]]
        return min(diffs) * 0.8 if diffs else 0.8

    def _draw_preview(self, *_args) -> None:
        if self._preview_figure is None or self._preview_canvas is None:
            return
        self._preview_stack.setCurrentWidget(self._plot_preview_panel)
        self._preview_figure.clear()
        axis = self._preview_figure.add_subplot(111)
        if not self._preview_xs or not self._preview_ys:
            axis.text(0.5, 0.5, "选择数据后显示绘图预览", ha="center", va="center", transform=axis.transAxes)
            axis.set_axis_off()
            self._preview_canvas.draw()
            return

        plot_type = self._preview_type_combo.currentText()
        if plot_type == "散点":
            axis.scatter(self._preview_xs, self._preview_ys, s=22, color="#0078D4")
        elif plot_type == "折线+点":
            axis.plot(self._preview_xs, self._preview_ys, marker="o", linewidth=1.5, markersize=4.2, color="#0078D4")
        elif plot_type == "柱状":
            axis.bar(self._preview_xs, self._preview_ys, width=self._preview_bar_width(self._preview_xs), color="#0078D4", alpha=0.85)
        elif plot_type == "阶梯":
            axis.step(self._preview_xs, self._preview_ys, where="mid", linewidth=1.5, color="#0078D4")
        else:
            axis.plot(self._preview_xs, self._preview_ys, linewidth=1.8, color="#0078D4")

        axis.set_title(self._preview_name or "数据预览")
        axis.set_xlabel(self._preview_x_label or "X")
        axis.set_ylabel(self._preview_y_label or "Y")
        axis.grid(True, alpha=0.2)
        self._preview_figure.tight_layout()
        self._preview_canvas.draw()

    def _show_xy_preview(self, xs, ys, name: str, x_label: str = "X", y_label: str = "Y"):
        """填充绘图预览和统计摘要。"""
        n = min(len(xs), len(ys))
        self._preview_xs = [float(value) for value in xs[:n]]
        self._preview_ys = [float(value) for value in ys[:n]]
        self._preview_name = name
        self._preview_x_label = x_label or "X"
        self._preview_y_label = y_label or "Y"
        self._draw_preview()

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

    def _show_text_preview(self, title: str, content: str, stats_text: str) -> None:
        self._preview_xs = []
        self._preview_ys = []
        self._preview_name = title
        self._preview_x_label = "X"
        self._preview_y_label = "Y"
        self._text_preview.setPlainText(content.strip())
        self._preview_stack.setCurrentWidget(self._text_preview)
        self._stats_label.setText(stats_text)

    def _show_image_preview(self, image_id: str, image_name: str) -> bool:
        image = project_manager.get_image(image_id)
        if image is None:
            return False
        image_path = project_manager.get_image_path(image_id)
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            self._image_preview_label.setPixmap(QPixmap())
            self._image_preview_label.setText(f"无法加载图片预览\n\n{image_path or '未找到图片路径'}")
            stats_text = f"图像名称: {image_name}\n曲线数量: {len(image.curves)}"
        else:
            target_width = max(320, self.width() - 220)
            target_height = 320
            scaled = pixmap.scaled(
                target_width,
                target_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._image_preview_label.setPixmap(scaled)
            self._image_preview_label.setText("")
            stats_text = (
                f"图像名称: {image_name}\n"
                f"尺寸: {pixmap.width()} × {pixmap.height()} px\n"
                f"曲线数量: {len(image.curves)}"
            )
        self._preview_stack.setCurrentWidget(self._image_preview_label)
        self._preview_name = image_name
        self._preview_xs = []
        self._preview_ys = []
        self._stats_label.setText(stats_text)
        return True

    def _show_folder_preview(self, node) -> None:
        project = project_manager.current_project
        if project is None or project.tree is None or node is None:
            self._clear_preview()
            return

        child_nodes = project_manager.get_children(node.id)
        folder_count = sum(1 for child in child_nodes if child.kind == "folder")
        data_count = sum(1 for child in child_nodes if child.kind == "data_file")
        image_count = sum(1 for child in child_nodes if child.kind == "image_work")
        analysis_count = sum(1 for child in child_nodes if child.kind == "analysis_result")
        preview_lines = [
            f"文件夹: {node.name or '未命名文件夹'}",
            "",
            f"直接子文件夹: {folder_count}",
            f"数据文件: {data_count}",
            f"图像: {image_count}",
            f"分析结果: {analysis_count}",
        ]
        self._show_text_preview(node.name or "文件夹", "\n".join(preview_lines), "当前节点为文件夹，支持摘要预览和管理操作。")

    def _show_analysis_result_preview(self, node_id: str) -> bool:
        project = project_manager.current_project
        if project is None or project.tree is None:
            return False
        node = project.tree.get_node(node_id)
        if node is None or node.kind != "analysis_result":
            return False
        analysis = project.find_analysis(node.analysis_id)
        if analysis is None:
            return False

        summary = analysis.summary or {}
        preview_lines = [
            f"名称: {analysis.name or '未命名分析结果'}",
            f"类型: {summary.get('analysis_type') or analysis.analysis_type or '-'}",
            f"数据来源: {summary.get('source_name', '-')}",
            f"创建时间: {analysis.created_at}",
        ]
        metric_pairs = [
            ("模型", summary.get("model")),
            ("方程", summary.get("equation")),
            ("R²", summary.get("r2")),
            ("相关系数", summary.get("r")),
            ("样本数", summary.get("n")),
            ("MAE", summary.get("mae")),
            ("RMSE", summary.get("rmse")),
            ("峰值数量", len(summary.get("peaks", []) or [])),
            ("波谷数量", len(summary.get("valleys", []) or [])),
        ]
        for label, value in metric_pairs:
            if value not in (None, "", [], {}):
                preview_lines.append(f"{label}: {value}")

        stats_text = "分析结果支持在分析页查看完整图表、摘要表和报告预览。"
        self._show_text_preview(analysis.name or "分析结果", "\n".join(preview_lines), stats_text)
        return True

    def _show_data_file_preview(self, node_id: str) -> bool:
        project = project_manager.current_project
        if project is None or project.tree is None:
            return False
        node = project.tree.get_node(node_id)
        if node is None or node.kind != "data_file":
            return False
        data_file = project.find_data_file(node.data_file_id)
        if data_file is None:
            return False
        if data_file.series:
            series = data_file.series[0]
            self._selected_type = "series"
            self._selected_id = series.id
            self._show_xy_preview(series.x, series.y, series.name, series.x_label, series.y_label)
            self._stats_label.setText(
                f"数据文件: {data_file.name}\n系列数量: {len(data_file.series)}\n\n{self._stats_label.text()}"
            )
            return True
        self._show_text_preview(data_file.name or "数据文件", f"数据文件: {data_file.name}\n\n当前数据文件中暂无数据系列。", "当前节点为数据文件，但文件内尚无数据可绘制。")
        return True

    def _set_actions_enabled(self, enabled: bool):
        self._btn_to_vis.setEnabled(enabled)
        self._btn_to_proc.setEnabled(enabled)
        self._btn_export.setEnabled(enabled)

    def _clone_series(self, series: DataSeries, *, name: Optional[str] = None) -> DataSeries:
        return DataSeries(
            name=name or series.name,
            x=list(series.x),
            y=list(series.y),
            y_err=list(series.y_err or []) if getattr(series, "y_err", None) else None,
            color=series.color,
            source=series.source,
            source_curve_id=series.source_curve_id,
            x_label=series.x_label,
            y_label=series.y_label,
        )

    def _build_data_file_copy_for_selection(self) -> Optional[DataFile]:
        project = project_manager.current_project
        if project is None or not self._selected_node_kind or not self._selected_node_id:
            return None
        base_name = self._current_node_name() or "copied_data"
        if self._selected_node_kind == "data_file":
            node = self._current_tree_node()
            if node is None:
                return None
            source = project.find_data_file(node.data_file_id)
            if source is None:
                return None
            series_list = [self._clone_series(series) for series in source.series]
            return DataFile(name=f"{base_name}_copy", series=series_list)
        if self._selected_node_kind in {"series", "curve"}:
            source_series = project_manager.get_series_from_node(self._selected_node_kind, self._selected_node_id)
            if source_series is None:
                return None
            return DataFile(name=f"{base_name}_copy", series=[self._clone_series(source_series)])
        return None

    def _apply_rename_current_node(self) -> None:
        new_name = self._manage_name_edit.text().strip()
        if not new_name or not self._selected_node_kind or not self._selected_node_id:
            return
        ok = False
        if self._selected_node_kind in {"folder", "data_file"}:
            ok = project_manager.rename_node(self._selected_node_id, new_name)
        elif self._selected_node_kind == "series":
            ok = project_manager.rename_series(self._selected_node_id, new_name)
        elif self._selected_node_kind == "curve":
            ok = project_manager.rename_curve(self._selected_node_id, new_name)
        elif self._selected_node_kind == "image_work":
            node = self._current_tree_node()
            if node is not None:
                ok = project_manager.rename_image(node.image_work_id, new_name)
                if ok:
                    node.name = new_name
        if not ok:
            InfoBar.warning("提示", "当前节点不支持重命名", parent=self, position=InfoBarPosition.TOP)
            return
        self.project_modified.emit()
        self.refresh()
        self.on_tree_node_selected(self._selected_node_kind, self._selected_node_id)
        InfoBar.success("已更新", new_name, parent=self, position=InfoBarPosition.TOP)

    def _duplicate_current_node_as_data_file(self) -> None:
        data_file = self._build_data_file_copy_for_selection()
        if data_file is None:
            InfoBar.warning("提示", "当前节点不支持复制为数据文件", parent=self, position=InfoBarPosition.TOP)
            return
        node = project_manager.add_data_file(data_file, parent_id=self._current_dataset_parent_id())
        if node is None:
            InfoBar.error("复制失败", "未能创建新的数据文件", parent=self, position=InfoBarPosition.TOP)
            return
        self.project_modified.emit()
        self.refresh()
        self.on_tree_node_selected("data_file", node.id)
        InfoBar.success("已复制", data_file.name, parent=self, position=InfoBarPosition.TOP)

    def _delete_current_node(self) -> None:
        if not self._selected_node_kind or not self._selected_node_id:
            return

        target_name = self._current_node_name() or self._selected_node_id
        dialog = MessageBox("确认删除", f"确定删除当前节点“{target_name}”吗？", self)
        if not dialog.exec():
            return

        ok = False
        if self._selected_node_kind in {"folder", "data_file"}:
            ok = project_manager.delete_node(self._selected_node_id)
        elif self._selected_node_kind == "series":
            ok = project_manager.delete_series(self._selected_node_id)
        elif self._selected_node_kind == "curve":
            ok = project_manager.delete_curve(self._selected_node_id)
        elif self._selected_node_kind == "image_work":
            node = self._current_tree_node()
            if node is not None:
                ok = project_manager.remove_image(node.image_work_id) is not None
                if ok:
                    ok = project_manager.delete_node(self._selected_node_id)
        if not ok:
            InfoBar.warning("提示", "当前节点删除失败或不支持删除", parent=self, position=InfoBarPosition.TOP)
            return

        self._selected_node_kind = None
        self._selected_node_id = None
        self._selected_type = None
        self._selected_id = None
        self.project_modified.emit()
        self.refresh()
        InfoBar.success("已删除", target_name, parent=self, position=InfoBarPosition.TOP)

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
            target_data_file_id = dlg.get_target_data_file_id()
            if target_data_file_id:
                data_file = project_manager.get_data_file(target_data_file_id)
                if data_file is None:
                    InfoBar.warning("提示", "所选目标数据文件不存在", parent=self, position=InfoBarPosition.TOP)
                    return
                appended = 0
                for series in series_list:
                    if project_manager.add_series_to_data_file(target_data_file_id, series):
                        appended += 1
                if appended != len(series_list):
                    InfoBar.warning("提示", "部分数据系列追加失败", parent=self, position=InfoBarPosition.TOP)
                    return
                self.refresh()
                self.project_modified.emit()
                InfoBar.success(
                    "导入成功",
                    f"已导入 {len(series_list)} 条数据系列到数据文件 {data_file.name}",
                    parent=self,
                    position=InfoBarPosition.TOP,
                )
                return
            df = DataFile(name=dlg.get_file_name(), series=series_list)
            project_manager.add_data_file(df, parent_id=self._current_dataset_parent_id())
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
        dlg = _NameDialog("新建数据集", "数据集名称:", "新数据集", self)
        if dlg.exec():
            name = dlg.get_name()
            if name:
                from models.schemas import DataFile
                df = DataFile(name=name)
                node = project_manager.add_data_file(df, parent_id=self._current_dataset_parent_id())
                if node is not None:
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
        self._selected_node_kind = kind
        self._selected_node_id = node_id
        self._shared_tree_hint.setText(f"当前共享树节点: {kind} / {node_id}")
        if kind == "data_file" and self._show_data_file_preview(node_id):
            self._set_actions_enabled(True)
            self._refresh_management_panel()
            return
        if kind in ("series", "curve"):
            series = project_manager.get_series_from_node(kind, node_id)
            if series and series.x:
                self._selected_type = "series" if kind == "series" else "curve"
                self._selected_id = series.id
                self._show_xy_preview(series.x, series.y, series.name, series.x_label, series.y_label)
                self._set_actions_enabled(True)
                self._refresh_management_panel()
                return
        if kind == "image_work":
            node = self._current_tree_node()
            image_id = getattr(node, "image_work_id", None) if node is not None else None
            if image_id and self._show_image_preview(image_id, self._current_node_name() or "图像"):
                self._selected_type = None
                self._selected_id = None
                self._set_actions_enabled(False)
                self._refresh_management_panel()
                return
        if kind == "analysis_result" and self._show_analysis_result_preview(node_id):
            self._selected_type = None
            self._selected_id = None
            self._set_actions_enabled(False)
            self._refresh_management_panel()
            return
        if kind == "folder":
            self._selected_type = None
            self._selected_id = None
            self._show_folder_preview(self._current_tree_node())
            self._set_actions_enabled(False)
            self._refresh_management_panel()
            return
        self._selected_type = None
        self._selected_id = None
        self._clear_preview()
        self._refresh_management_panel()


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
