"""数据管理页

三区域布局：左侧数据树 | 右上数据预览表格 | 右下统计摘要
支持从 PyLine 图像提取曲线复制为独立 DataSeries，以及文件导入。
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEvent, Qt, Signal, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFontMetrics, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidgetItem, QAbstractItemView,
    QFileDialog, QFrame, QLabel, QPushButton,
    QSizePolicy, QStackedWidget,
)
from qfluentwidgets import (
    BreadcrumbBar,
    ComboBox,
    CardWidget, ToolButton, PushButton, PrimaryPushButton,
    TreeWidget, BodyLabel, CaptionLabel, PlainTextEdit,
    FluentIcon as FIF, InfoBar, InfoBarPosition,
    MessageBox, MessageBoxBase, LineEdit, TabCloseButtonDisplayMode,
    TabWidget, TeachingTipTailPosition, ToolTipFilter, ToolTipPosition, isDarkTheme,
)

from ui.theme import (
    WORKBENCH_BUTTON_HEIGHT,
    WORKBENCH_BUTTON_MIN_WIDTH,
    WORKBENCH_TOOL_PANEL_WIDTH,
    apply_button_metrics,
    accent_color, border_color, card_background_color,
    hover_color, secondary_color, surface_color, text_color,
    make_inline_label, make_section_label, make_hsep,
)
from ui.matplotlib_fonts import configure_matplotlib_cjk
from ui.widgets.onboarding import OnboardingStep, PageOnboardingController
from core.shortcut_manager import ShortcutBindingSet
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
_SOURCE_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
_TEXT_PREVIEW_SUFFIXES = {".csv", ".txt", ".dat", ".tsv", ".json", ".md", ".log", ".py", ".yaml", ".yml", ".ini"}
_TABULAR_PREVIEW_SUFFIXES = {".xlsx", ".xls", ".npy", ".npz"}


class DataPage(QWidget):
    """数据管理页：统一管理图像提取曲线和导入数据集。"""

    send_to_visualize = Signal(str, str)   # (type: "curve"|"series", id)
    send_to_process   = Signal(str, str)   # (type, id)
    project_modified  = Signal()
    tree_filter_kinds = ["folder", "source_file", "data_file", "image_work", "series", "curve", "analysis_result"]

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
        self._pending_import_paths: list[str] = []
        self._external_browser_dir: Optional[Path] = None
        self._show_hidden_browser_entries = False
        self._shortcut_bindings = ShortcutBindingSet()
        self._setup_ui()
        self._setup_shortcuts()
        self._onboarding_controller = PageOnboardingController(self, "data", self._data_onboarding_steps)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._onboarding_controller.schedule_auto_start()

    # ─────────────────────────────────────────────────────────
    # UI 构建
    # ─────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        self._content_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._content_splitter.setHandleWidth(4)
        self._tool_panel = self._build_manage_panel()
        self._content_splitter.addWidget(self._tool_panel)
        self._content_splitter.addWidget(self._build_right_panel())
        self._content_splitter.setStretchFactor(0, 0)
        self._content_splitter.setStretchFactor(1, 1)
        self._content_splitter.setSizes([WORKBENCH_TOOL_PANEL_WIDTH, 980])
        root.addWidget(self._content_splitter, 1)
        self._apply_preview_host_background()
        self._install_preview_drop_targets()

    def _setup_shortcuts(self) -> None:
        context = Qt.ShortcutContext.WidgetWithChildrenShortcut
        self._shortcut_bindings.bind("data_copy_curve_to_series", self, self._copy_curve_to_series, context=context)
        self._shortcut_bindings.bind("data_delete_selected", self, self._delete_selected, context=context)
        self._shortcut_bindings.bind("data_apply_rename", self, self._apply_rename_current_node, context=context)
        self._shortcut_bindings.bind("data_delete_node", self, self._delete_current_node, context=context)

    def apply_shortcuts(self) -> None:
        self._shortcut_bindings.apply()

    def start_onboarding(self, force: bool = False) -> None:
        self._onboarding_controller.start(force=force)

    def _data_onboarding_steps(self) -> list[OnboardingStep]:
        return [
            OnboardingStep(
                lambda: self._tool_panel,
                TeachingTipTailPosition.BOTTOM,
                "先在共享树里选对象",
                "左侧共享项目树是唯一入口；选中对象后，这里的节点管理和右侧文件管理会自动切换。",
            ),
            OnboardingStep(
                lambda: self._preview_type_combo,
                TeachingTipTailPosition.BOTTOM,
                "先看预览",
                "切换折线、散点或柱状，先确认导入结果和异常点。",
            ),
            OnboardingStep(
                lambda: self._manage_target_label,
                TeachingTipTailPosition.LEFT_BOTTOM,
                "当前节点在这里管理",
                "按节点类型，这里会切换成重命名、直接导入或待导入管理。",
            ),
            OnboardingStep(
                lambda: self._btn_to_vis,
                TeachingTipTailPosition.BOTTOM,
                "确认后继续流转",
                "数据无误后，可直接送到可视化或处理页。",
            ),
        ]

    def eventFilter(self, watched, event):
        preview_targets = getattr(self, "_preview_drop_targets", ())
        if watched in preview_targets:
            if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
                file_path = self._supported_drop_file_path(event.mimeData())
                if file_path:
                    event.acceptProposedAction()
                else:
                    event.ignore()
                return True
            if event.type() == QEvent.Type.Drop:
                file_path = self._supported_drop_file_path(event.mimeData())
                if not file_path:
                    event.ignore()
                    return True
                event.acceptProposedAction()
                self._import_file(file_path)
                return True
        return super().eventFilter(watched, event)

    def _install_preview_drop_targets(self) -> None:
        targets = [self._preview_stack, self._plot_preview_panel, self._image_preview_label, self._text_preview]
        if self._preview_canvas is not None:
            targets.append(self._preview_canvas)
        self._preview_drop_targets = tuple(targets)
        for widget in self._preview_drop_targets:
            widget.setAcceptDrops(True)
            widget.installEventFilter(self)

    @staticmethod
    def _supported_drop_file_path(mime_data) -> Optional[str]:
        if mime_data is None or not mime_data.hasUrls():
            return None
        from ui.dialogs.import_dialog import SUPPORTED_IMPORT_SUFFIXES

        allowed_suffixes = set(SUPPORTED_IMPORT_SUFFIXES)
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            file_path = url.toLocalFile()
            if Path(file_path).suffix.lower() in allowed_suffixes:
                return file_path
        return None

    def _apply_preview_host_background(self) -> None:
        dark = isDarkTheme()
        bg = "#1e1e1e" if dark else "#ffffff"
        fg = "#cccccc" if dark else "#222222"
        self._plot_preview_panel.setStyleSheet(f"background: {bg};")
        if self._preview_canvas is not None:
            self._preview_canvas.setStyleSheet(f"background: {bg};")
        if hasattr(self, "_preview_canvas_label"):
            self._preview_canvas_label.setStyleSheet(f"background: {bg}; color: {fg};")
        preview_surface = surface_color()
        preview_border = border_color()
        self._image_preview_label.setStyleSheet(
            f"background: {preview_surface}; color: {fg};"
            f" border: 1px solid {preview_border}; border-radius: 12px; padding: 12px;"
        )
        self._text_preview.setStyleSheet(
            "QPlainTextEdit {"
            f"background: {preview_surface};"
            f"color: {fg};"
            f"border: 1px solid {preview_border};"
            "border-radius: 12px;"
            "padding: 8px;"
            "}"
        )

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

    def _build_manage_panel(self) -> QWidget:
        panel = CardWidget(self)
        panel.setFixedWidth(WORKBENCH_TOOL_PANEL_WIDTH)
        manage_layout = QVBoxLayout(panel)
        manage_layout.setContentsMargins(14, 14, 14, 14)
        manage_layout.setSpacing(10)

        manage_layout.addWidget(make_section_label("节点管理"))
        self._manage_target_label = CaptionLabel("[未选择] 节点", panel)
        self._manage_target_label.setWordWrap(True)
        self._manage_target_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        manage_layout.addWidget(self._manage_target_label)

        self._manage_type_label = CaptionLabel("", panel)
        self._manage_type_label.setWordWrap(True)
        self._manage_type_label.hide()
        manage_layout.addWidget(self._manage_type_label)
        self._apply_muted_summary_label_style(self._manage_target_label, self._manage_type_label)

        self._manage_help_label = CaptionLabel("数据文件、系列、图像和源文件会按当前节点能力开放管理动作。", panel)
        self._manage_help_label.setWordWrap(True)
        self._apply_muted_summary_label_style(self._manage_help_label)
        manage_layout.addWidget(self._manage_help_label)

        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(6)
        name_row.addWidget(make_inline_label("名称:", panel, width=42))
        self._manage_name_edit = LineEdit(panel)
        self._manage_name_edit.setPlaceholderText("选择节点后可编辑名称")
        name_row.addWidget(self._manage_name_edit, 1)
        self._btn_apply_name = PushButton("重命名", panel)
        self._btn_apply_name.clicked.connect(self._apply_rename_current_node)
        apply_button_metrics(self._btn_apply_name, min_width=84)
        self._btn_apply_name.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        name_row.addWidget(self._btn_apply_name)
        manage_layout.addLayout(name_row)

        manage_layout.addWidget(make_hsep())

        primary_row = QHBoxLayout()
        self._btn_delete_node = PushButton(FIF.DELETE, "删除节点", panel)
        self._btn_delete_node.clicked.connect(self._delete_current_node)
        self._apply_panel_button_metrics(self._btn_delete_node)
        primary_row.addWidget(self._btn_delete_node, 1)
        self._btn_export = PushButton("导出数据", panel)
        self._btn_export.clicked.connect(self._export_csv)
        self._apply_panel_button_metrics(self._btn_export)
        primary_row.addWidget(self._btn_export, 1)
        manage_layout.addLayout(primary_row)

        action_row = QHBoxLayout()
        self._btn_to_vis = PrimaryPushButton(FIF.PIE_SINGLE, "→ 可视化")
        self._btn_to_proc = PushButton(FIF.DEVELOPER_TOOLS, "→ 处理")
        self._btn_to_vis.clicked.connect(self._send_to_visualize)
        self._btn_to_proc.clicked.connect(self._send_to_process)
        self._apply_panel_button_metrics(self._btn_to_vis, self._btn_to_proc)
        action_row.addWidget(self._btn_to_vis, 1)
        action_row.addWidget(self._btn_to_proc, 1)
        manage_layout.addLayout(action_row)

        self._source_file_action_panel = QWidget(panel)
        self._source_file_action_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        source_file_action_row = QHBoxLayout(self._source_file_action_panel)
        source_file_action_row.setContentsMargins(0, 0, 0, 0)
        source_file_action_row.setSpacing(6)
        self._btn_import_source_to_data = PrimaryPushButton(FIF.DICTIONARY_ADD, "导入到数据集", self._source_file_action_panel)
        self._btn_import_source_to_data.clicked.connect(self._import_current_source_file_to_dataset)
        self._btn_import_source_to_digitize = PushButton(FIF.PHOTO, "导入到数据化", self._source_file_action_panel)
        self._btn_import_source_to_digitize.clicked.connect(self._import_current_source_file_to_digitize)
        self._apply_panel_button_metrics(
            self._btn_import_source_to_data,
            self._btn_import_source_to_digitize,
        )
        source_file_action_row.addWidget(self._btn_import_source_to_data, 1)
        source_file_action_row.addWidget(self._btn_import_source_to_digitize, 1)
        manage_layout.addWidget(self._source_file_action_panel)

        self._import_queue_panel = QWidget(panel)
        self._import_queue_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        queue_layout = QVBoxLayout(self._import_queue_panel)
        queue_layout.setContentsMargins(0, 0, 0, 0)
        queue_layout.setSpacing(10)

        queue_layout.addWidget(make_hsep())
        queue_layout.addWidget(make_section_label("待导入列表"))

        self._pending_source_hint = CaptionLabel("右侧文件管理器负责选择外部文件；这里负责查看、移除和执行导入。", self._import_queue_panel)
        self._pending_source_hint.setWordWrap(True)
        self._pending_source_hint.hide()
        queue_layout.addWidget(self._pending_source_hint)

        self._pending_source_list = TreeWidget(self._import_queue_panel)
        self._pending_source_list.setHeaderHidden(True)
        self._pending_source_list.setMinimumHeight(260)
        self._pending_source_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._pending_source_list.itemSelectionChanged.connect(self._refresh_pending_source_controls)
        queue_layout.addWidget(self._pending_source_list, 1)

        pending_row = QHBoxLayout()
        self._btn_remove_pending = PushButton("移除所选", self._import_queue_panel)
        self._btn_remove_pending.clicked.connect(self._remove_selected_pending_source_files)
        self._btn_clear_pending = PushButton("清空列表", self._import_queue_panel)
        self._btn_clear_pending.clicked.connect(self._clear_pending_source_files)
        self._apply_panel_button_metrics(self._btn_remove_pending, self._btn_clear_pending)
        pending_row.addWidget(self._btn_remove_pending, 1)
        pending_row.addWidget(self._btn_clear_pending, 1)
        queue_layout.addLayout(pending_row)

        import_row = QHBoxLayout()
        self._btn_import_pending = PrimaryPushButton(FIF.DOWNLOAD, "执行导入", self._import_queue_panel)
        self._btn_import_pending.clicked.connect(self._import_pending_files_for_current_group)
        self._apply_panel_button_metrics(self._btn_import_pending)
        import_row.addWidget(self._btn_import_pending, 1)
        queue_layout.addLayout(import_row)
        manage_layout.addWidget(self._import_queue_panel, 1)

        self._manage_bottom_spacer = QWidget(panel)
        self._manage_bottom_spacer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        manage_layout.addWidget(self._manage_bottom_spacer, 1)

        self._set_management_actions_enabled(False)
        self._source_file_action_panel.hide()
        self._import_queue_panel.hide()
        self._manage_bottom_spacer.show()
        self._refresh_pending_source_list()
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._right_mode_stack = QStackedWidget(panel)
        layout.addWidget(self._right_mode_stack, stretch=3)

        self._preview_card = CardWidget(panel)
        preview_layout = QVBoxLayout(self._preview_card)
        preview_layout.setContentsMargins(14, 14, 14, 14)
        preview_layout.setSpacing(10)

        preview_header = QHBoxLayout()
        preview_header.addWidget(make_section_label("数据预览"))
        preview_header.addStretch()
        self._preview_plot_type_controls = QWidget(self._preview_card)
        preview_plot_type_layout = QHBoxLayout(self._preview_plot_type_controls)
        preview_plot_type_layout.setContentsMargins(0, 0, 0, 0)
        preview_plot_type_layout.setSpacing(6)
        preview_plot_type_layout.addWidget(CaptionLabel("图型", self._preview_card))
        self._preview_type_combo = ComboBox(self._preview_card)
        self._preview_type_combo.setFixedHeight(WORKBENCH_BUTTON_HEIGHT)
        self._preview_type_combo.setMinimumWidth(120)
        self._preview_type_combo.addItems(["折线", "散点", "折线+点", "柱状", "阶梯"])
        self._preview_type_combo.currentIndexChanged.connect(self._draw_preview)
        preview_plot_type_layout.addWidget(self._preview_type_combo)
        preview_header.addWidget(self._preview_plot_type_controls)
        preview_layout.addLayout(preview_header)

        self._preview_stack = QStackedWidget(self._preview_card)
        preview_layout.addWidget(self._preview_stack, stretch=3)

        self._plot_preview_panel = QWidget(self._preview_card)
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
                self._preview_card,
            )
            self._preview_canvas_label.setWordWrap(True)
            self._preview_canvas_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            plot_preview_layout.addWidget(self._preview_canvas_label, stretch=1)

        self._preview_stack.addWidget(self._plot_preview_panel)

        self._image_preview_label = QLabel(self._preview_card)
        self._image_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_preview_label.setMinimumHeight(240)
        self._image_preview_label.setWordWrap(True)
        self._preview_stack.addWidget(self._image_preview_label)

        self._text_preview = PlainTextEdit(self._preview_card)
        self._text_preview.setReadOnly(True)
        self._text_preview.setMinimumHeight(240)
        self._preview_stack.addWidget(self._text_preview)

        preview_layout.addWidget(make_hsep())

        preview_layout.addWidget(make_section_label("统计摘要"))
        self._stats_label = BodyLabel("（选择数据后显示统计信息）")
        self._stats_label.setWordWrap(True)
        self._stats_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._apply_summary_label_style(self._stats_label)
        preview_layout.addWidget(self._stats_label)

        self._source_path_panel = QWidget(self._preview_card)
        source_path_layout = QVBoxLayout(self._source_path_panel)
        source_path_layout.setContentsMargins(0, 0, 0, 0)
        source_path_layout.setSpacing(6)

        current_path_row = QHBoxLayout()
        current_path_row.setContentsMargins(0, 0, 0, 0)
        current_path_row.addWidget(make_inline_label("当前路径:", self._source_path_panel, width=72))
        self._current_source_path_button = self._create_path_link_button(self._source_path_panel)
        current_path_row.addWidget(self._current_source_path_button, 1)
        source_path_layout.addLayout(current_path_row)

        origin_path_row = QHBoxLayout()
        origin_path_row.setContentsMargins(0, 0, 0, 0)
        origin_path_row.addWidget(make_inline_label("源路径:", self._source_path_panel, width=72))
        self._origin_source_path_button = self._create_path_link_button(self._source_path_panel)
        origin_path_row.addWidget(self._origin_source_path_button, 1)
        source_path_layout.addLayout(origin_path_row)
        preview_layout.addWidget(self._source_path_panel)

        self._source_manager_card = self._build_source_manager_card(panel)
        self._right_mode_stack.addWidget(self._preview_card)
        self._right_mode_stack.addWidget(self._source_manager_card)
        self._set_actions_enabled(False)
        self._set_preview_plot_type_controls_visible(False)
        self._set_source_path_links_visible(False)
        return panel

    def _set_preview_plot_type_controls_visible(self, visible: bool) -> None:
        self._preview_plot_type_controls.setVisible(visible)

    def _build_source_manager_card(self, parent: QWidget) -> CardWidget:
        card = CardWidget(parent)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        layout.addWidget(make_section_label("文件管理器"))
        self._source_manager_hint = CaptionLabel("这里显示系统文件；可切换目录、浏览文件，并把外部文件加入左侧待导入列表。", card)
        self._source_manager_hint.setWordWrap(True)
        self._source_manager_hint.hide()
        layout.addWidget(self._source_manager_hint)

        self._source_manager_target_label = BodyLabel("导入目标: -", card)
        self._source_manager_target_label.setWordWrap(True)
        self._apply_summary_label_style(self._source_manager_target_label)
        layout.addWidget(self._source_manager_target_label)

        self._source_browser_tabs = TabWidget(card)
        self._source_browser_tabs.tabBar.setAddButtonVisible(False)
        self._source_browser_tabs.tabBar.setCloseButtonDisplayMode(TabCloseButtonDisplayMode.NEVER)
        self._source_browser_tabs.stackedWidget.currentChanged.connect(self._refresh_source_manager_tab_state)

        project_source_page = QWidget(card)
        project_source_layout = QVBoxLayout(project_source_page)
        project_source_layout.setContentsMargins(0, 0, 0, 0)
        project_source_layout.setSpacing(10)

        self._project_source_hint = CaptionLabel("这里显示项目中的源文件，可直接加入左侧待导入列表。", project_source_page)
        self._project_source_hint.setWordWrap(True)
        self._project_source_hint.hide()
        project_source_layout.addWidget(self._project_source_hint)

        self._project_source_browser = TreeWidget(project_source_page)
        self._project_source_browser.setHeaderHidden(True)
        self._project_source_browser.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._project_source_browser.itemSelectionChanged.connect(self._refresh_project_source_controls)
        self._project_source_browser.itemDoubleClicked.connect(self._on_project_source_item_activated)
        project_source_layout.addWidget(self._project_source_browser, 1)

        self._project_source_detail_label = CaptionLabel("未选择项目源文件", project_source_page)
        self._project_source_detail_label.setWordWrap(True)
        self._project_source_detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._apply_summary_label_style(self._project_source_detail_label)
        project_source_layout.addWidget(self._project_source_detail_label)

        project_source_row = QHBoxLayout()
        self._btn_add_selected_project_sources = PrimaryPushButton(FIF.ADD, "添加选中源文件", project_source_page)
        self._btn_add_selected_project_sources.clicked.connect(self._add_selected_project_source_files_to_pending)
        self._apply_panel_button_metrics(self._btn_add_selected_project_sources)
        project_source_row.addWidget(self._btn_add_selected_project_sources, 1)
        project_source_layout.addLayout(project_source_row)
        self._source_browser_tabs.addTab(project_source_page, "源文件")

        system_page = QWidget(card)
        system_layout = QVBoxLayout(system_page)
        system_layout.setContentsMargins(0, 0, 0, 0)

        browser_row = QHBoxLayout()
        self._btn_choose_browser_dir = PushButton("选择目录", system_page)
        self._btn_choose_browser_dir.clicked.connect(self._choose_external_browser_dir)
        self._btn_browser_up = PushButton("上一级", system_page)
        self._btn_browser_up.clicked.connect(self._go_to_external_browser_parent)
        self._btn_toggle_hidden_browser = ToolButton(getattr(FIF, "VIEW", FIF.SEARCH), system_page)
        self._btn_toggle_hidden_browser.clicked.connect(self._toggle_hidden_browser_entries)
        self._btn_refresh_browser = ToolButton(FIF.SYNC, system_page)
        self._btn_refresh_browser.setToolTip("刷新当前目录")
        self._btn_refresh_browser.clicked.connect(self._refresh_source_browser)
        self._apply_panel_button_metrics(self._btn_choose_browser_dir, self._btn_browser_up)
        self._btn_toggle_hidden_browser.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)
        self._btn_refresh_browser.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)
        self._btn_toggle_hidden_browser.installEventFilter(ToolTipFilter(self._btn_toggle_hidden_browser, 300, ToolTipPosition.TOP))
        self._btn_refresh_browser.installEventFilter(ToolTipFilter(self._btn_refresh_browser, 300, ToolTipPosition.TOP))
        browser_row.addWidget(self._btn_choose_browser_dir, 1)
        browser_row.addWidget(self._btn_browser_up, 1)
        browser_row.addWidget(self._btn_toggle_hidden_browser)
        browser_row.addWidget(self._btn_refresh_browser)
        system_layout.addLayout(browser_row)
        system_layout.setSpacing(10)
        self._update_hidden_browser_toggle_button()

        self._source_breadcrumb_bar = BreadcrumbBar(system_page)
        self._source_breadcrumb_bar.currentItemChanged.connect(self._on_source_breadcrumb_changed)
        system_layout.addWidget(self._source_breadcrumb_bar)

        self._source_browser = TreeWidget(system_page)
        self._source_browser.setHeaderHidden(True)
        self._source_browser.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._source_browser.itemSelectionChanged.connect(self._refresh_source_browser_controls)
        self._source_browser.itemDoubleClicked.connect(self._on_source_browser_item_activated)
        system_layout.addWidget(self._source_browser, 1)

        self._source_browser_detail_label = CaptionLabel("未选择系统文件", system_page)
        self._source_browser_detail_label.setWordWrap(True)
        self._source_browser_detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._apply_summary_label_style(self._source_browser_detail_label)
        system_layout.addWidget(self._source_browser_detail_label)

        system_action_row = QHBoxLayout()
        self._btn_add_selected_sources = PrimaryPushButton(FIF.ADD, "添加选中文件", system_page)
        self._btn_add_selected_sources.clicked.connect(self._add_selected_browser_source_files_to_pending)
        self._apply_panel_button_metrics(self._btn_add_selected_sources)
        system_action_row.addWidget(self._btn_add_selected_sources, 1)
        system_layout.addLayout(system_action_row)
        self._source_browser_tabs.addTab(system_page, "系统文件")

        layout.addWidget(self._source_browser_tabs, 1)
        return card

    def _apply_panel_button_metrics(self, *buttons) -> None:
        apply_button_metrics(*buttons, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        for button in buttons:
            if button is None:
                continue
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _apply_summary_label_style(self, *labels) -> None:
        style = f"color: {text_color()}; font-size: 12px; font-weight: 500;"
        for label in labels:
            if label is None:
                continue
            label.setStyleSheet(style)

    def _apply_muted_summary_label_style(self, *labels) -> None:
        style = f"color: {secondary_color()}; font-size: 11px; font-weight: 400;"
        for label in labels:
            if label is None:
                continue
            label.setStyleSheet(style)

    def _create_path_link_button(self, parent: QWidget) -> QPushButton:
        button = QPushButton(parent)
        button.setFlat(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedHeight(WORKBENCH_BUTTON_HEIGHT)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.setStyleSheet(
            "QPushButton {"
            f"color: {accent_color()};"
            "background: transparent;"
            "border: none;"
            "padding: 0;"
            "text-align: left;"
            "font-weight: 500;"
            "text-decoration: underline;"
            "}"
            "QPushButton:hover {"
            f"color: {accent_color()};"
            "}"
            "QPushButton:disabled {"
            f"color: {secondary_color()};"
            "text-decoration: none;"
            "}"
        )
        button.installEventFilter(ToolTipFilter(button, 300, ToolTipPosition.TOP))
        button.clicked.connect(lambda _checked=False, source=button: self._open_path_button_target(source))
        return button

    def _refresh_path_link_button_text(self, button: QPushButton) -> None:
        raw_text = str(button.property("fullText") or "")
        empty_text = str(button.property("emptyText") or "未记录")
        display_text = raw_text or empty_text
        if raw_text:
            metrics = QFontMetrics(button.font())
            available_width = max(button.width() - 8, 24)
            display_text = metrics.elidedText(raw_text, Qt.TextElideMode.ElideMiddle, available_width)
        button.setText(display_text)

    def _open_path_button_target(self, button: QPushButton) -> None:
        self._open_path_in_folder(str(button.property("targetPath") or ""))

    def _set_path_link_button(self, button: QPushButton, file_path: str, empty_text: str = "未记录") -> None:
        target_path = file_path.strip()
        button.setProperty("targetPath", target_path)
        button.setProperty("fullText", target_path)
        button.setProperty("emptyText", empty_text)
        button.setToolTip(target_path or empty_text)
        button.setEnabled(bool(target_path))
        self._refresh_path_link_button_text(button)

    def _set_source_path_links_visible(self, visible: bool) -> None:
        self._source_path_panel.setVisible(visible)

    @staticmethod
    def _source_file_icon_for_path(file_path: str):
        suffix = Path(file_path).suffix.lower()
        return FIF.PHOTO if suffix in _SOURCE_IMAGE_SUFFIXES else FIF.DOCUMENT

    def _show_source_path_links(self, current_path: str, origin_path: str) -> None:
        self._set_path_link_button(self._current_source_path_button, current_path, "未记录当前路径")
        self._set_path_link_button(self._origin_source_path_button, origin_path, "未记录源路径")
        self._set_source_path_links_visible(True)

    def _hide_source_path_links(self) -> None:
        self._set_path_link_button(self._current_source_path_button, "", "未记录当前路径")
        self._set_path_link_button(self._origin_source_path_button, "", "未记录源路径")
        self._set_source_path_links_visible(False)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_current_source_path_button"):
            self._refresh_path_link_button_text(self._current_source_path_button)
        if hasattr(self, "_origin_source_path_button"):
            self._refresh_path_link_button_text(self._origin_source_path_button)

    def _refresh_source_breadcrumbs(self, browser_dir: Optional[Path]) -> None:
        self._source_breadcrumb_bar.blockSignals(True)
        self._source_breadcrumb_bar.clear()
        if browser_dir is None:
            self._source_breadcrumb_bar.blockSignals(False)
            return

        try:
            normalized = browser_dir.resolve()
        except OSError:
            normalized = browser_dir

        parts = normalized.parts
        if not parts:
            self._source_breadcrumb_bar.blockSignals(False)
            return

        if normalized.anchor:
            anchor_path = Path(normalized.anchor)
            anchor_label = normalized.anchor or str(anchor_path)
            self._source_breadcrumb_bar.addItem(str(anchor_path), anchor_label)
            current_path = anchor_path
            index_start = 1
        else:
            current_path = Path(parts[0])
            self._source_breadcrumb_bar.addItem(str(current_path), parts[0])
            index_start = 1

        for part in parts[index_start:]:
            current_path = current_path / part
            self._source_breadcrumb_bar.addItem(str(current_path), part)
        self._source_breadcrumb_bar.blockSignals(False)

    def _on_source_breadcrumb_changed(self, route_key: str) -> None:
        if not route_key:
            return
        self._navigate_external_browser_to(Path(route_key))

    def _navigate_external_browser_to(self, target_path: Path) -> None:
        self._external_browser_dir = target_path
        self._refresh_source_browser()

    def _open_path_in_folder(self, file_path: str) -> None:
        if not file_path:
            InfoBar.warning("提示", "当前没有可打开的路径", parent=self, position=InfoBarPosition.TOP)
            return

        path = Path(file_path).expanduser()
        target = path if path.is_dir() else path.parent
        if not target.exists():
            InfoBar.warning("提示", f"路径不存在: {target}", parent=self, position=InfoBarPosition.TOP)
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))):
            InfoBar.error("打开失败", str(target), parent=self, position=InfoBarPosition.TOP)

    def _source_files_root_node(self):
        project = project_manager.current_project
        if project is None or project.tree is None:
            return None
        for node in project.tree.nodes:
            if node.kind != "folder":
                continue
            if getattr(node, "parent_id", None) is not None:
                continue
            if self._canonical_folder_group(getattr(node, "group_type", None)) == "source_files":
                return node
        return None

    @staticmethod
    def _sorted_node_children(parent_id: str):
        return sorted(
            project_manager.get_children(parent_id),
            key=lambda child: (getattr(child, "kind", "") != "folder", getattr(child, "name", "").lower()),
        )

    def _refresh_project_source_browser(self) -> None:
        self._project_source_browser.clear()
        self._project_source_detail_label.setText("未选择项目源文件")
        source_root = self._source_files_root_node()
        if source_root is None:
            self._refresh_project_source_controls()
            return

        group_type = self._current_import_group()

        def append_children(parent_item, parent_id: str) -> None:
            for child in self._sorted_node_children(parent_id):
                if child.kind not in {"folder", "source_file"}:
                    continue
                item = QTreeWidgetItem([child.name or "未命名节点"])
                item.setData(0, Qt.ItemDataRole.UserRole, getattr(child, "id", ""))
                item.setData(0, Qt.ItemDataRole.UserRole + 1, child.kind)
                if child.kind == "folder":
                    item.setIcon(0, FIF.FOLDER.icon())
                    item.setToolTip(0, child.name or "未命名文件夹")
                    parent_item.addChild(item)
                    append_children(item, child.id)
                    continue

                file_path = project_manager.get_source_file_path(getattr(child, "source_file_id", ""))
                asset = project_manager.get_source_file(getattr(child, "source_file_id", ""))
                source_origin_path = "" if asset is None else asset.source_file_path
                display_name = child.name or Path(file_path).name or "未命名源文件"
                if group_type in {"datasets", "images"} and file_path and not self._supports_group_import(group_type, file_path):
                    display_name = f"{display_name}  ·  当前模式不支持"
                item.setText(0, display_name)
                item.setIcon(0, self._source_file_icon_for_path(file_path).icon())
                item.setData(0, Qt.ItemDataRole.UserRole + 2, file_path)
                item.setData(0, Qt.ItemDataRole.UserRole + 3, source_origin_path)
                item.setToolTip(0, file_path or display_name)
                parent_item.addChild(item)

        for child in self._sorted_node_children(source_root.id):
            if child.kind not in {"folder", "source_file"}:
                continue
            item = QTreeWidgetItem([child.name or "未命名节点"])
            item.setData(0, Qt.ItemDataRole.UserRole, getattr(child, "id", ""))
            item.setData(0, Qt.ItemDataRole.UserRole + 1, child.kind)
            if child.kind == "folder":
                item.setIcon(0, FIF.FOLDER.icon())
                item.setToolTip(0, child.name or "未命名文件夹")
                self._project_source_browser.addTopLevelItem(item)
                append_children(item, child.id)
                item.setExpanded(True)
                continue

            file_path = project_manager.get_source_file_path(getattr(child, "source_file_id", ""))
            asset = project_manager.get_source_file(getattr(child, "source_file_id", ""))
            source_origin_path = "" if asset is None else asset.source_file_path
            display_name = child.name or Path(file_path).name or "未命名源文件"
            if group_type in {"datasets", "images"} and file_path and not self._supports_group_import(group_type, file_path):
                display_name = f"{display_name}  ·  当前模式不支持"
            item.setText(0, display_name)
            item.setIcon(0, self._source_file_icon_for_path(file_path).icon())
            item.setData(0, Qt.ItemDataRole.UserRole + 2, file_path)
            item.setData(0, Qt.ItemDataRole.UserRole + 3, source_origin_path)
            item.setToolTip(0, file_path or display_name)
            self._project_source_browser.addTopLevelItem(item)

        self._refresh_project_source_controls()

    def _selected_project_source_items(self) -> list[QTreeWidgetItem]:
        return [
            item
            for item in self._project_source_browser.selectedItems()
            if item.data(0, Qt.ItemDataRole.UserRole + 1) == "source_file"
        ]

    def _selected_project_source_file_paths(self) -> list[str]:
        paths: list[str] = []
        for item in self._selected_project_source_items():
            file_path = item.data(0, Qt.ItemDataRole.UserRole + 2)
            if file_path:
                paths.append(str(file_path))
        return paths

    def _refresh_project_source_controls(self) -> None:
        selected_items = self._selected_project_source_items()
        selected_paths = self._selected_project_source_file_paths()
        group_type = self._current_import_group()
        supported_paths = [path for path in selected_paths if group_type is not None and self._supports_group_import(group_type, path)]
        self._btn_add_selected_project_sources.setEnabled(group_type in {"datasets", "images"} and bool(supported_paths))

        if not selected_items:
            self._project_source_detail_label.setText("未选择项目源文件")
            return

        first_item = selected_items[0]
        current_path = str(first_item.data(0, Qt.ItemDataRole.UserRole + 2) or "")
        origin_path = str(first_item.data(0, Qt.ItemDataRole.UserRole + 3) or "")
        detail = [f"已选 {len(selected_items)} 个源文件", f"当前路径: {current_path or '-'}"]
        if origin_path:
            detail.append(f"导入源路径: {origin_path}")
        if group_type in {"datasets", "images"} and len(supported_paths) < len(selected_paths):
            detail.append("部分文件当前目标不支持，加入待导入列表时会自动跳过。")
        self._project_source_detail_label.setText("\n".join(detail))

    def _add_selected_project_source_files_to_pending(self) -> None:
        selected_paths = self._selected_project_source_file_paths()
        if not selected_paths:
            return
        added = self._append_source_files_to_pending(selected_paths)
        if added:
            InfoBar.success("已加入列表", f"新增 {added} 个源文件", parent=self, position=InfoBarPosition.TOP)
        else:
            InfoBar.info("提示", "所选源文件未加入列表，可能已存在或当前模式不支持", parent=self, position=InfoBarPosition.TOP)

    def _on_project_source_item_activated(self, item, _column: int) -> None:
        if item.data(0, Qt.ItemDataRole.UserRole + 1) == "folder":
            item.setExpanded(not item.isExpanded())
            return
        file_path = item.data(0, Qt.ItemDataRole.UserRole + 2)
        if file_path:
            self._append_source_files_to_pending([str(file_path)])

    def _refresh_source_manager_tab_state(self) -> None:
        if not hasattr(self, "_project_source_browser"):
            return
        if self._source_browser_tabs.tabBar.count() < 2:
            return
        group_type = self._current_import_group()
        use_project_sources = group_type in {"datasets", "images"}
        self._source_browser_tabs.tabBar.setVisible(use_project_sources)
        if not use_project_sources:
            self._source_browser_tabs.setCurrentIndex(1)
        self._refresh_source_browser_controls()
        self._refresh_project_source_controls()

    # ─────────────────────────────────────────────────────────
    # 树刷新
    # ─────────────────────────────────────────────────────────

    def refresh(self):
        """刷新页面状态。"""
        self._clear_preview()
        self._refresh_pending_source_list()
        p = project_manager.current_project
        if p is None:
            self._selected_node_kind = None
            self._selected_node_id = None
        self._refresh_management_panel()

    def _clear_preview(self):
        self._show_preview_mode()
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
        self._set_preview_plot_type_controls_visible(False)
        self._hide_source_path_links()
        self._set_actions_enabled(False)

    def _set_management_actions_enabled(self, enabled: bool) -> None:
        self._manage_name_edit.setEnabled(enabled)
        self._btn_apply_name.setEnabled(enabled)
        self._btn_delete_node.setEnabled(enabled)

    def _show_preview_mode(self) -> None:
        self._right_mode_stack.setCurrentWidget(self._preview_card)

    def _show_source_manager_mode(self) -> None:
        self._right_mode_stack.setCurrentWidget(self._source_manager_card)

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
        if group_type in {"source_files"}:
            return "source_files"
        if group_type in {"image_set", "images"}:
            return "images"
        if group_type in {"picture_set", "pictures"}:
            return "pictures"
        if group_type in {"tool_set", "tools"}:
            return "tools"
        if group_type in {"template_group", "figure_template_group"}:
            return "figure_template_group"
        return group_type

    def _folder_collection_group(self, node) -> Optional[str]:
        current = node
        while current is not None and getattr(current, "kind", None) == "folder":
            group_type = self._canonical_folder_group(getattr(current, "group_type", None))
            if group_type in {"source_files", "datasets", "images", "pictures", "analysis_result_group"}:
                return group_type
            parent_id = getattr(current, "parent_id", None)
            current = project_manager.get_node_by_id(parent_id) if parent_id else None
        return None

    def _is_protected_folder_node(self, node) -> bool:
        if node is None or getattr(node, "kind", None) != "folder":
            return False
        group_type = self._canonical_folder_group(getattr(node, "group_type", None))
        if group_type in {"source_files", "datasets", "images", "pictures", "analysis_result_group"}:
            return getattr(node, "parent_id", None) is None
        return group_type in {
            "tools", "pipeline_group", "figure_template_group",
            "report_template_group", "ai_group", "prompt_group",
            "skill_group", "agent_group",
        }

    def _current_import_group(self) -> Optional[str]:
        node = self._current_tree_node()
        if node is None or getattr(node, "kind", None) != "folder":
            return None
        group_type = self._folder_collection_group(node)
        if group_type in {"datasets", "images", "source_files"}:
            return group_type
        return None

    def _current_import_target_folder_id(self) -> Optional[str]:
        node = self._current_tree_node()
        if node is None or getattr(node, "kind", None) != "folder":
            return None
        if self._current_import_group() is None:
            return None
        return getattr(node, "id", None)

    @staticmethod
    def _format_file_size(file_size: int) -> str:
        if file_size >= 1024 * 1024:
            return f"{file_size / (1024 * 1024):.1f} MB"
        if file_size >= 1024:
            return f"{file_size / 1024:.1f} KB"
        return f"{file_size} B"

    def _supports_dataset_import(self, file_path: str) -> bool:
        from ui.dialogs.import_dialog import SUPPORTED_IMPORT_SUFFIXES

        return Path(file_path).suffix.lower() in set(SUPPORTED_IMPORT_SUFFIXES)

    @staticmethod
    def _supports_digitize_import(file_path: str) -> bool:
        return Path(file_path).suffix.lower() in _SOURCE_IMAGE_SUFFIXES

    def _supports_group_import(self, group_type: Optional[str], file_path: str) -> bool:
        if group_type == "datasets":
            return self._supports_dataset_import(file_path)
        if group_type == "images":
            return self._supports_digitize_import(file_path)
        if group_type == "source_files":
            return Path(file_path).is_file()
        return False

    def _current_source_file_asset(self):
        node = self._current_tree_node()
        if node is None or getattr(node, "kind", None) != "source_file":
            return None
        return project_manager.get_source_file(getattr(node, "source_file_id", ""))

    def _current_source_file_path(self) -> str:
        asset = self._current_source_file_asset()
        if asset is None:
            return ""
        return project_manager.get_source_file_path(asset.id)

    def _ensure_external_browser_dir(self) -> Optional[Path]:
        if self._external_browser_dir is not None and self._external_browser_dir.exists() and self._external_browser_dir.is_dir():
            return self._external_browser_dir
        self._external_browser_dir = Path.home()
        return self._external_browser_dir

    def _update_hidden_browser_toggle_button(self) -> None:
        if not hasattr(self, "_btn_toggle_hidden_browser"):
            return
        showing_hidden = bool(self._show_hidden_browser_entries)
        tooltip = "隐藏隐藏文件" if showing_hidden else "显示隐藏文件"
        icon = getattr(FIF, "HIDE", FIF.CANCEL) if showing_hidden else getattr(FIF, "VIEW", FIF.SEARCH)
        self._btn_toggle_hidden_browser.setIcon(icon.icon())
        self._btn_toggle_hidden_browser.setToolTip(tooltip)

    def _toggle_hidden_browser_entries(self) -> None:
        self._show_hidden_browser_entries = not self._show_hidden_browser_entries
        self._update_hidden_browser_toggle_button()
        self._refresh_source_browser()

    def _pending_entry_label(self, file_path: str) -> str:
        path = Path(file_path)
        try:
            size_text = self._format_file_size(path.stat().st_size)
        except OSError:
            size_text = "-"
        return f"{path.name}  ·  {size_text}"

    def _refresh_source_browser(self) -> None:
        browser_dir = self._ensure_external_browser_dir()
        self._source_browser.clear()
        self._source_browser_detail_label.setText("未选择系统文件")
        group_type = self._current_import_group()

        if browser_dir is None:
            self._refresh_source_breadcrumbs(None)
            self._refresh_source_browser_controls()
            return

        self._refresh_source_breadcrumbs(browser_dir)
        try:
            entries = sorted(
                (
                    entry for entry in browser_dir.iterdir()
                    if self._show_hidden_browser_entries or not entry.name.startswith(".")
                ),
                key=lambda entry: (entry.is_file(), entry.name.lower()),
            )
        except OSError as exc:
            self._source_browser_detail_label.setText(f"无法读取目录: {exc}")
            self._refresh_source_browser_controls()
            return

        for entry in entries:
            item = QTreeWidgetItem([entry.name])
            item.setData(0, Qt.ItemDataRole.UserRole, str(entry))
            item.setData(0, Qt.ItemDataRole.UserRole + 1, "dir" if entry.is_dir() else "file")
            item.setToolTip(0, str(entry))
            if entry.is_dir():
                item.setIcon(0, FIF.FOLDER.icon())
            else:
                item.setIcon(0, self._source_file_icon_for_path(str(entry)).icon())
                if group_type is not None and not self._supports_group_import(group_type, str(entry)):
                    item.setText(0, f"{entry.name}  ·  当前模式不支持")
            self._source_browser.addTopLevelItem(item)

        self._refresh_source_browser_controls()

    def _selected_browser_file_paths(self) -> list[str]:
        result: list[str] = []
        for item in self._source_browser.selectedItems():
            file_path = item.data(0, Qt.ItemDataRole.UserRole)
            entry_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if file_path and entry_type == "file":
                result.append(str(file_path))
        return result

    def _refresh_source_browser_controls(self) -> None:
        selected_paths = self._selected_browser_file_paths()
        current_dir = self._ensure_external_browser_dir()
        self._btn_browser_up.setEnabled(current_dir is not None and current_dir.parent != current_dir)
        self._btn_add_selected_sources.setEnabled(bool(selected_paths))
        if selected_paths:
            first_path = Path(selected_paths[0])
            detail = [f"已选 {len(selected_paths)} 个文件", f"路径: {first_path}"]
            try:
                detail.append(f"大小: {self._format_file_size(first_path.stat().st_size)}")
            except OSError:
                pass
            self._source_browser_detail_label.setText("\n".join(detail))
            return
        self._source_browser_detail_label.setText("未选择系统文件")

    def _selected_pending_source_file_ids(self) -> list[str]:
        result: list[str] = []
        for item in self._pending_source_list.selectedItems():
            file_path = item.data(0, Qt.ItemDataRole.UserRole)
            if file_path:
                result.append(str(file_path))
        return result

    def _refresh_pending_source_list(self) -> None:
        valid_paths: list[str] = []
        self._pending_source_list.clear()
        for file_path in self._pending_import_paths:
            path = Path(file_path)
            if not path.exists() or not path.is_file():
                continue
            valid_paths.append(str(path))
            item = QTreeWidgetItem([self._pending_entry_label(str(path))])
            item.setData(0, Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(0, str(path))
            self._pending_source_list.addTopLevelItem(item)
        self._pending_import_paths = valid_paths
        self._refresh_pending_source_controls()

    def _refresh_pending_source_controls(self) -> None:
        group_type = self._current_import_group()
        has_items = bool(self._pending_import_paths)
        has_selection = bool(self._selected_pending_source_file_ids())
        self._btn_remove_pending.setEnabled(has_selection)
        self._btn_clear_pending.setEnabled(has_items)
        self._btn_import_pending.setEnabled(has_items and group_type is not None)

        if group_type == "datasets":
            self._btn_import_pending.setText("导入到数据集")
        elif group_type == "images":
            self._btn_import_pending.setText("导入到数据化")
        elif group_type == "source_files":
            self._btn_import_pending.setText("导入为源文件")
        else:
            self._btn_import_pending.setText("执行导入")

        if has_items:
            if group_type == "source_files":
                self._pending_source_hint.setText(f"当前共 {len(self._pending_import_paths)} 个外部文件待导入为源文件。")
            elif group_type == "datasets":
                self._pending_source_hint.setText(f"当前共 {len(self._pending_import_paths)} 个待导入文件，将导入到数据集。")
            elif group_type == "images":
                self._pending_source_hint.setText(f"当前共 {len(self._pending_import_paths)} 个待导入文件，将导入到数据化。")
            else:
                self._pending_source_hint.setText(f"当前共 {len(self._pending_import_paths)} 个待导入文件。")
        else:
            if group_type in {"datasets", "images"}:
                self._pending_source_hint.setText("右侧可从系统文件或项目源文件中选取项目，加入这里后统一执行导入。")
            else:
                self._pending_source_hint.setText("右侧文件管理器负责选择外部文件；这里负责查看、移除和执行导入。")

    def _append_source_files_to_pending(self, file_paths: list[str]) -> int:
        group_type = self._current_import_group()
        added = 0
        for file_path in file_paths:
            normalized = str(Path(file_path).resolve())
            path = Path(normalized)
            if not path.exists() or not path.is_file():
                continue
            if group_type is not None and not self._supports_group_import(group_type, normalized):
                continue
            if normalized in self._pending_import_paths:
                continue
            self._pending_import_paths.append(normalized)
            added += 1
        self._refresh_pending_source_list()
        return added

    def _remove_pending_source_files(self, file_paths: list[str]) -> None:
        to_remove = set(file_paths)
        self._pending_import_paths = [
            file_path
            for file_path in self._pending_import_paths
            if file_path not in to_remove
        ]
        self._refresh_pending_source_list()

    def _add_current_source_file_to_pending(self) -> None:
        self._import_current_source_file_to_dataset()

    def _add_selected_browser_source_files_to_pending(self) -> None:
        selected_paths = self._selected_browser_file_paths()
        if not selected_paths:
            return
        added = self._append_source_files_to_pending(selected_paths)
        if added:
            InfoBar.success("已加入列表", f"新增 {added} 个外部文件", parent=self, position=InfoBarPosition.TOP)
        else:
            InfoBar.info("提示", "所选文件未加入列表，可能已存在或当前模式不支持", parent=self, position=InfoBarPosition.TOP)

    def _remove_selected_pending_source_files(self) -> None:
        selected_paths = self._selected_pending_source_file_ids()
        if not selected_paths:
            return
        self._remove_pending_source_files(selected_paths)

    def _clear_pending_source_files(self) -> None:
        if not self._pending_import_paths:
            return
        self._pending_import_paths = []
        self._refresh_pending_source_list()

    def _choose_external_browser_dir(self) -> None:
        start_dir = str(self._ensure_external_browser_dir() or Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "选择系统目录", start_dir)
        if not chosen:
            return
        self._external_browser_dir = Path(chosen)
        self._refresh_source_browser()

    def _go_to_external_browser_parent(self) -> None:
        current_dir = self._ensure_external_browser_dir()
        if current_dir is None or current_dir.parent == current_dir:
            return
        self._external_browser_dir = current_dir.parent
        self._refresh_source_browser()

    def _on_source_browser_item_activated(self, item, _column: int) -> None:
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        entry_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if not file_path:
            return
        path = Path(str(file_path))
        if entry_type == "dir":
            self._external_browser_dir = path
            self._refresh_source_browser()
            return
        self._append_source_files_to_pending([str(path)])

    def _show_source_file_manager(self) -> None:
        self._show_source_manager_mode()
        group_type = self._current_import_group()
        target_name = self._current_node_name() or "未命名节点"
        group_label = {
            "datasets": "数据集",
            "images": "数据化",
            "source_files": "源文件",
        }.get(group_type, "-")
        self._source_manager_target_label.setText(f"导入目标: {group_label} / {target_name}")
        if group_type == "datasets":
            self._source_browser_tabs.setCurrentIndex(0)
            self._stats_label.setText("在这里浏览系统文件并导入到当前数据集文件夹。")
        elif group_type == "images":
            self._source_browser_tabs.setCurrentIndex(0)
            self._stats_label.setText("在这里浏览系统图片并导入到当前数据化文件夹。")
        else:
            self._source_browser_tabs.setCurrentIndex(1)
            self._stats_label.setText("在这里浏览系统文件并导入为当前源文件文件夹下的源文件节点。")
        self._refresh_source_manager_tab_state()
        self._refresh_project_source_browser()
        self._refresh_source_browser()

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
            "source_file": "源文件",
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
        if self._selected_node_kind in {"source_file", "data_file", "series", "curve", "image_work"}:
            return True
        if self._selected_node_kind == "folder":
            return not self._is_protected_folder_node(self._current_tree_node())
        return False

    def _can_delete_current_node(self) -> bool:
        if not self._selected_node_kind or not self._selected_node_id:
            return False
        if self._selected_node_kind in {"source_file", "data_file", "series", "curve", "image_work"}:
            return True
        if self._selected_node_kind == "folder":
            return not self._is_protected_folder_node(self._current_tree_node())
        return False

    def _refresh_management_panel(self) -> None:
        import_group = self._current_import_group()
        is_source_file_leaf = self._selected_node_kind == "source_file"
        self._btn_to_vis.setVisible(not is_source_file_leaf)
        self._btn_to_proc.setVisible(not is_source_file_leaf)
        self._source_file_action_panel.setVisible(bool(is_source_file_leaf))
        self._import_queue_panel.setVisible(import_group is not None)
        self._manage_bottom_spacer.setVisible(import_group is None)

        if not self._selected_node_kind or not self._selected_node_id:
            self._manage_target_label.setText("[未选择] 节点")
            self._manage_type_label.setText("")
            self._manage_name_edit.clear()
            self._set_management_actions_enabled(False)
            self._btn_export.setEnabled(False)
            self._source_file_action_panel.hide()
            self._import_queue_panel.hide()
            self._refresh_pending_source_controls()
            return

        current_name = self._current_node_name() or "未命名节点"
        self._manage_target_label.setText(f"[{self._node_kind_label(self._selected_node_kind)}] {current_name}")
        self._manage_type_label.setText("")
        self._manage_name_edit.setText(current_name)
        enabled = self._can_rename_current_node() or self._can_delete_current_node()
        self._manage_name_edit.setEnabled(self._can_rename_current_node())
        self._btn_apply_name.setEnabled(self._can_rename_current_node())
        self._btn_delete_node.setEnabled(self._can_delete_current_node())
        if is_source_file_leaf or import_group is not None:
            self._btn_export.setEnabled(False)
        if not enabled:
            self._manage_help_label.setText("当前节点仅支持预览，不支持直接管理操作。")
        elif is_source_file_leaf:
            source_path = self._current_source_file_path()
            self._btn_import_source_to_data.setEnabled(bool(source_path) and self._supports_dataset_import(source_path))
            self._btn_import_source_to_digitize.setEnabled(bool(source_path) and self._supports_digitize_import(source_path))
            self._manage_help_label.setText("源文件节点支持重命名、删除，以及按文件类型直接导入到数据集或数据化。")
        elif import_group == "source_files":
            self._manage_help_label.setText("源文件文件夹可重命名/删除；右侧文件管理器用于浏览系统文件并导入为源文件。")
        elif import_group == "datasets":
            self._manage_help_label.setText("数据集文件夹可重命名/删除；右侧文件管理器用于浏览外部数据文件并导入到当前数据集目录。")
        elif import_group == "images":
            self._manage_help_label.setText("数据化文件夹可重命名/删除；右侧文件管理器用于浏览系统图片并导入到当前数据化目录。")
        else:
            self._manage_help_label.setText("数据文件、系列、图像和分析结果按当前节点能力开放重命名、删除、导出或继续流转。")
        self._refresh_pending_source_controls()

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
        self._apply_preview_host_background()
        self._preview_figure.clear()
        axis = self._preview_figure.add_subplot(111)
        dark = isDarkTheme()
        bg = "#1e1e1e" if dark else "#ffffff"
        fg = "#cccccc" if dark else "#222222"
        gc = "#444444" if dark else "#dddddd"
        self._preview_figure.patch.set_facecolor(bg)
        axis.set_facecolor(bg)
        axis.tick_params(colors=fg, labelcolor=fg)
        for spine in axis.spines.values():
            spine.set_edgecolor(fg)
        if not self._preview_xs or not self._preview_ys:
            axis.text(
                0.5,
                0.5,
                "选择数据后显示绘图预览",
                ha="center",
                va="center",
                color=fg,
                transform=axis.transAxes,
            )
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

        axis.set_title(self._preview_name or "数据预览", color=fg)
        axis.set_xlabel(self._preview_x_label or "X", color=fg)
        axis.set_ylabel(self._preview_y_label or "Y", color=fg)
        axis.grid(True, color=gc, alpha=0.35)
        self._preview_figure.tight_layout()
        self._preview_canvas.draw()

    def _show_xy_preview(self, xs, ys, name: str, x_label: str = "X", y_label: str = "Y"):
        """填充绘图预览和统计摘要。"""
        self._show_preview_mode()
        self._set_preview_plot_type_controls_visible(True)
        self._hide_source_path_links()
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
        self._show_preview_mode()
        self._set_preview_plot_type_controls_visible(False)
        self._hide_source_path_links()
        self._preview_xs = []
        self._preview_ys = []
        self._preview_name = title
        self._preview_x_label = "X"
        self._preview_y_label = "Y"
        self._text_preview.setPlainText(content.strip())
        self._preview_stack.setCurrentWidget(self._text_preview)
        self._stats_label.setText(stats_text)

    def _show_image_preview(self, image_id: str, image_name: str) -> bool:
        self._show_preview_mode()
        self._set_preview_plot_type_controls_visible(False)
        self._hide_source_path_links()
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
        source_count = sum(1 for child in child_nodes if child.kind == "source_file")
        data_count = sum(1 for child in child_nodes if child.kind == "data_file")
        image_count = sum(1 for child in child_nodes if child.kind == "image_work")
        analysis_count = sum(1 for child in child_nodes if child.kind == "analysis_result")
        preview_lines = [
            f"文件夹: {node.name or '未命名文件夹'}",
            "",
            f"直接子文件夹: {folder_count}",
            f"源文件: {source_count}",
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

    def _show_source_file_preview(self, node_id: str) -> bool:
        project = project_manager.current_project
        if project is None or project.tree is None:
            return False
        node = project.tree.get_node(node_id)
        if node is None or node.kind != "source_file":
            return False
        asset = project_manager.get_source_file(node.source_file_id)
        file_path = project_manager.get_source_file_path(node.source_file_id)
        if not file_path:
            return False

        path = Path(file_path)
        origin_path = "" if asset is None else asset.source_file_path
        stats_lines = [
            f"文件名: {node.name or path.name}",
            f"类型: {path.suffix.lower() or '-'}",
        ]
        try:
            stats_lines.append(f"大小: {self._format_file_size(path.stat().st_size)}")
        except OSError:
            pass

        if path.suffix.lower() in _SOURCE_IMAGE_SUFFIXES:
            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                self._show_text_preview(node.name or path.name, "无法加载图片预览。", "\n".join(stats_lines))
                return True
            self._show_preview_mode()
            target_width = max(320, self.width() - 220)
            target_height = 320
            self._image_preview_label.setPixmap(
                pixmap.scaled(
                    target_width,
                    target_height,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self._image_preview_label.setText("")
            self._preview_stack.setCurrentWidget(self._image_preview_label)
            self._stats_label.setText("\n".join(stats_lines))
            self._show_source_path_links(str(path), origin_path)
            return True

        if path.suffix.lower() in _TEXT_PREVIEW_SUFFIXES:
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                content = f"无法读取文本预览: {exc}"
            preview_text = content[:4000]
            if len(content) > 4000:
                preview_text += "\n\n... 已截断 ..."
            self._show_text_preview(node.name or path.name, preview_text, "\n".join(stats_lines))
            self._show_source_path_links(str(path), origin_path)
            return True

        preview_lines = [f"文件名: {node.name or path.name}"]
        if path.suffix.lower() in _TABULAR_PREVIEW_SUFFIXES:
            preview_lines.append("该文件类型暂不提供内联全文预览，但支持作为数据文件导入。")
        else:
            preview_lines.append("该文件类型暂不提供内联预览，可使用下方导入动作继续流转。")
        preview_lines.append("")
        preview_lines.extend(stats_lines[1:])
        self._show_text_preview(node.name or path.name, "\n".join(preview_lines), "\n".join(stats_lines))
        self._show_source_path_links(str(path), origin_path)
        return True

    def _set_actions_enabled(self, enabled: bool):
        self._btn_to_vis.setEnabled(enabled)
        self._btn_to_proc.setEnabled(enabled)
        self._btn_export.setEnabled(enabled)

    def _import_current_source_file_to_dataset(self) -> None:
        source_path = self._current_source_file_path()
        if not source_path or not self._supports_dataset_import(source_path):
            InfoBar.warning("提示", "当前源文件类型不支持导入到数据集", parent=self, position=InfoBarPosition.TOP)
            return
        self._import_file(source_path)

    def _import_current_source_file_to_digitize(self) -> None:
        asset = self._current_source_file_asset()
        source_path = self._current_source_file_path()
        if asset is None or not source_path or not self._supports_digitize_import(source_path):
            InfoBar.warning("提示", "当前源文件类型不支持导入到数据化", parent=self, position=InfoBarPosition.TOP)
            return
        current_selection = (self._selected_node_kind, self._selected_node_id)
        try:
            project_manager.add_image(source_path, name=asset.name)
        except ValueError as exc:
            InfoBar.warning("导入失败", str(exc), parent=self, position=InfoBarPosition.TOP)
            return
        self.project_modified.emit()
        self.refresh()
        if current_selection[0] and current_selection[1]:
            self.on_tree_node_selected(current_selection[0], current_selection[1])
        InfoBar.success("导入成功", f"已导入到数据化: {asset.name}", parent=self, position=InfoBarPosition.TOP)

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
        if self._selected_node_kind in {"folder", "data_file", "source_file"}:
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
            InfoBar.warning(
                "重命名失败",
                project_manager.get_last_error_message() or "当前节点不支持重命名",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return
        self.project_modified.emit()
        self.refresh()
        self.on_tree_node_selected(self._selected_node_kind, self._selected_node_id)
        InfoBar.success("已更新", new_name, parent=self, position=InfoBarPosition.TOP)

    def _duplicate_current_node_as_data_file(self) -> None:
        InfoBar.info("提示", "“复制为数据文件”功能已移除，请改用导入文件或源文件待导入列表。", parent=self, position=InfoBarPosition.TOP)

    def _delete_current_node(self) -> None:
        if not self._selected_node_kind or not self._selected_node_id:
            return

        target_name = self._current_node_name() or self._selected_node_id
        dialog = MessageBox("确认删除", f"确定删除当前节点“{target_name}”吗？", self)
        if not dialog.exec():
            return

        ok = False
        if self._selected_node_kind in {"folder", "data_file", "source_file"}:
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

    def _create_import_dialog(self, file_path: Optional[str] = None):
        from ui.dialogs.import_dialog import ImportDialog

        dialog = ImportDialog(self)
        if file_path:
            dialog.load_file(file_path)
        return dialog

    def _apply_import_dialog_results(self, dialog, *, show_feedback: bool = True) -> bool:
        series_list = dialog.get_results()
        if not series_list:
            return False
        target_data_file_id = dialog.get_target_data_file_id()
        if target_data_file_id:
            data_file = project_manager.get_data_file(target_data_file_id)
            if data_file is None:
                if show_feedback:
                    InfoBar.warning("提示", "所选目标数据文件不存在", parent=self, position=InfoBarPosition.TOP)
                return False
            appended = 0
            for series in series_list:
                if project_manager.add_series_to_data_file(target_data_file_id, series):
                    appended += 1
            if appended != len(series_list):
                if show_feedback:
                    InfoBar.warning(
                        "导入失败",
                        project_manager.get_last_error_message() or "部分数据系列追加失败",
                        parent=self,
                        position=InfoBarPosition.TOP,
                    )
                return False
            if show_feedback:
                InfoBar.success(
                    "导入成功",
                    f"已导入 {len(series_list)} 条数据系列到数据文件 {data_file.name}",
                    parent=self,
                    position=InfoBarPosition.TOP,
                )
            return True

        data_file = DataFile(name=dialog.get_file_name(), series=series_list)
        node = project_manager.add_data_file(
            data_file,
            parent_id=self._current_dataset_parent_id(),
            auto_rename_on_conflict=True,
        )
        if node is None:
            if show_feedback:
                InfoBar.error(
                    "导入失败",
                    project_manager.get_last_error_message() or "未能创建新的数据文件",
                    parent=self,
                    position=InfoBarPosition.TOP,
                )
            return False
        if show_feedback:
            InfoBar.success(
                "导入成功",
                f"已导入 {len(series_list)} 条数据系列到数据文件 {data_file.name}",
                parent=self,
                position=InfoBarPosition.TOP,
            )
        return True

    def _import_pending_files_for_current_group(self) -> None:
        group_type = self._current_import_group()
        if group_type == "datasets":
            self._import_pending_source_files_to_datasets()
            return
        if group_type == "images":
            self._import_pending_source_files_to_digitize()
            return
        if group_type == "source_files":
            self._import_pending_files_as_source_files()

    def _import_pending_source_files_to_datasets(self) -> None:
        if not self._pending_import_paths:
            return

        completed_paths: list[str] = []
        failed_names: list[str] = []
        stopped = False
        current_selection = (self._selected_node_kind, self._selected_node_id)

        for file_path in list(self._pending_import_paths):
            path = Path(file_path)
            if not path.exists():
                failed_names.append(path.name)
                continue
            try:
                dialog = self._create_import_dialog(str(path))
            except Exception as exc:
                failed_names.append(path.name)
                InfoBar.warning("导入失败", f"无法读取文件 {path.name}: {exc}", parent=self, position=InfoBarPosition.TOP)
                continue
            if not dialog.exec():
                stopped = True
                break
            if self._apply_import_dialog_results(dialog, show_feedback=False):
                completed_paths.append(str(path))
            else:
                failed_names.append(path.name)

        if completed_paths:
            self._remove_pending_source_files(completed_paths)
            self.project_modified.emit()
            self.refresh()
            if current_selection[0] and current_selection[1]:
                self.on_tree_node_selected(current_selection[0], current_selection[1])

        summary = f"成功导入 {len(completed_paths)} 个文件到数据集"
        if failed_names:
            summary += f"，失败 {len(failed_names)} 个"
        if stopped:
            summary += "，导入在中途停止"
        if completed_paths:
            InfoBar.success("批量导入完成", summary, parent=self, position=InfoBarPosition.TOP)
        elif failed_names or stopped:
            InfoBar.warning("批量导入未完成", summary, parent=self, position=InfoBarPosition.TOP)

    def _import_pending_source_files_to_digitize(self) -> None:
        if not self._pending_import_paths:
            return

        completed_paths: list[str] = []
        skipped_names: list[str] = []
        current_selection = (self._selected_node_kind, self._selected_node_id)

        for file_path in list(self._pending_import_paths):
            path = Path(file_path)
            if not path.exists():
                skipped_names.append(path.name)
                continue
            if not self._supports_digitize_import(str(path)):
                skipped_names.append(path.name)
                continue
            try:
                project_manager.add_image(str(path), name=path.name)
            except ValueError:
                skipped_names.append(path.name)
                continue
            completed_paths.append(str(path))

        if completed_paths:
            self._remove_pending_source_files(completed_paths)
            self.project_modified.emit()
            self.refresh()
            if current_selection[0] and current_selection[1]:
                self.on_tree_node_selected(current_selection[0], current_selection[1])

        summary = f"成功导入 {len(completed_paths)} 个文件到数据化"
        if skipped_names:
            summary += f"，跳过 {len(skipped_names)} 个非图片文件"
        if completed_paths:
            InfoBar.success("批量导入完成", summary, parent=self, position=InfoBarPosition.TOP)
        else:
            InfoBar.warning("未导入任何文件", summary, parent=self, position=InfoBarPosition.TOP)

    def _import_pending_files_as_source_files(self) -> None:
        if not self._pending_import_paths:
            return

        current_selection = (self._selected_node_kind, self._selected_node_id)
        target_folder_id = self._current_import_target_folder_id()
        completed_paths: list[str] = []
        failed_names: list[str] = []

        for file_path in list(self._pending_import_paths):
            node = project_manager.add_source_file(
                file_path,
                parent_id=target_folder_id,
                auto_rename_on_conflict=True,
            )
            if node is not None:
                completed_paths.append(file_path)
            else:
                failed_names.append(Path(file_path).name)

        if completed_paths:
            self._remove_pending_source_files(completed_paths)
            self.project_modified.emit()
            self.refresh()
            if current_selection[0] and current_selection[1]:
                self.on_tree_node_selected(current_selection[0], current_selection[1])
            summary = f"成功导入 {len(completed_paths)} 个文件为源文件"
            if failed_names:
                summary += f"，失败 {len(failed_names)} 个"
            InfoBar.success("批量导入完成", summary, parent=self, position=InfoBarPosition.TOP)
            if failed_names:
                InfoBar.warning("部分导入失败", project_manager.get_last_error_message() or "存在同名源文件，已阻止导入", parent=self, position=InfoBarPosition.TOP)
            return

        InfoBar.warning(
            "未导入任何文件",
            project_manager.get_last_error_message() or "没有外部文件成功导入为源文件",
            parent=self,
            position=InfoBarPosition.TOP,
        )

    # ─────────────────────────────────────────────────────────
    # 操作：导入文件
    # ─────────────────────────────────────────────────────────

    def _import_file(self, file_path: Optional[str] = None):
        p = project_manager.current_project
        if p is None:
            InfoBar.warning("提示", "请先打开项目", parent=self, position=InfoBarPosition.TOP)
            return

        try:
            dialog = self._create_import_dialog(file_path)
        except Exception as exc:
            InfoBar.warning("导入失败", f"无法读取拖入文件：{exc}", parent=self, position=InfoBarPosition.TOP)
            return
        if dialog.exec() and self._apply_import_dialog_results(dialog, show_feedback=False):
            self.refresh()
            self.project_modified.emit()
            InfoBar.success("导入成功", "文件已导入到数据管理区", parent=self, position=InfoBarPosition.TOP)

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
        self._apply_preview_host_background()
        if self._preview_figure is not None and self._preview_canvas is not None:
            self._draw_preview()

    def on_tree_node_selected(self, kind: str, node_id: str) -> None:
        """共享树选中节点 → 显示预览。"""
        self._selected_node_kind = kind
        self._selected_node_id = node_id
        if kind == "source_file":
            self._selected_type = None
            self._selected_id = None
            self._show_source_file_preview(node_id)
            self._set_actions_enabled(False)
            self._refresh_management_panel()
            return
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
            if self._current_import_group() in {"datasets", "images", "source_files"}:
                self._show_source_file_manager()
                self._set_actions_enabled(False)
                self._refresh_management_panel()
                return
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
