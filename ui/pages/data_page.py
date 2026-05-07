"""数据管理页

三区域布局：左侧数据树 | 右上数据预览表格 | 右下统计摘要
支持从 PyLine 图像提取曲线复制为独立 DataSeries，以及文件导入。
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontMetrics, QIntValidator, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidgetItem, QAbstractItemView,
    QFileDialog, QFrame, QLabel, QMenu,
    QSizePolicy, QStackedWidget, QHeaderView, QTableWidgetItem,
)
from qfluentwidgets import (
    Action,
    BreadcrumbBar,
    ComboBox,
    CardWidget, ToolButton, PushButton, PrimaryPushButton,
    TreeWidget, BodyLabel, CaptionLabel, PlainTextEdit, RoundMenu, TableWidget, HyperlinkButton,
    FluentIcon as FIF, InfoBar, InfoBarPosition,
    MessageBox, MessageBoxBase, LineEdit, TabCloseButtonDisplayMode,
    TeachingTipTailPosition, ToolTip, ToolTipFilter, ToolTipPosition,
    SmoothScrollArea, SubtitleLabel, isDarkTheme,
)

from ui.theme import (
    WORKBENCH_BUTTON_HEIGHT,
    WORKBENCH_BUTTON_MIN_WIDTH,
    WORKBENCH_TOOL_PANEL_WIDTH,
    apply_button_metrics,
    accent_color, border_color, card_background_color,
    hover_color, preview_canvas_background_color, preview_canvas_foreground_color,
    secondary_color, surface_color, text_color,
    make_inline_label, make_section_label, make_hsep,
)
from ui.widgets.focus_commit import install_click_away_focus_commit
from ui.widgets.matplotlib_preview import (
    build_preview_toolbar,
    create_navigation_toolbar,
    preview_navigation_mode,
    sync_preview_nav_toggle_states,
    toggle_preview_box_zoom_mode,
    toggle_preview_pan_mode,
    zoom_figure_axes,
)
from ui.widgets.project_tree_support import folder_display_name, is_protected_folder
from ui.widgets.navigation_stack import SegmentedStackWidget
from ui.widgets.onboarding import OnboardingStep, PageOnboardingController
from core.extension_api import (
    build_extension_entry,
    extension_entry_display_info,
    extension_entry_parameter_help_text,
    extension_lines_support_text,
    extension_registry,
    normalize_extension_lines_number,
    validate_extension_lines_list,
)
from core.global_assets import global_assets, parse_plot_style_asset_key
from core.exporter import Exporter
from core.shortcut_manager import ShortcutBindingSet
from core.project_manager import project_manager
from core.ui_preferences import get_data_page_source_favorites, set_data_page_source_favorites
from models.schemas import Curve, CurveStyleTemplate, DataFile, DataSeries, Dataset, FigureConfig, PlotTheme, ReportTemplate, SavedPipeline
from app.workspaces.data_workspace import DataWorkspaceController, DataWorkspaceState
from ui.dialogs.export_flow import choose_curve_file_export_plan, curve_export_file_filter
from ui.dialogs.fluent_dialogs import TextInputDialog
from .data_page_support import (
    Figure,
    FigureCanvas,
    HAS_MATPLOTLIB,
    _EXTENSION_FIELD_HELP_COMPACT_HEIGHT,
    _EXTENSION_FIELD_HELP_EXPANDED_HEIGHT,
    _FOLDER_GROUP_LABELS,
    _MATPLOTLIB_ERROR,
    _NodeDetailDialog,
    _NodePreviewState,
    _PendingImportQueueState,
    _SOURCE_IMAGE_SUFFIXES,
    _TABULAR_PREVIEW_SUFFIXES,
    _TextActionLabel,
    _TEXT_PREVIEW_SUFFIXES,
    _TYPE_ANALYSIS,
    _TYPE_ANALYSIS_ROOT,
    _TYPE_CURVE,
    _TYPE_DATASET,
    _TYPE_IMAGE,
    _TYPE_ROOT,
    _TYPE_SERIES,
)
from .data_page_state_bridge import DataPageStateBridge


class DataPage(QWidget):
    """数据管理页：统一管理图像提取曲线和导入数据集。"""

    send_to_visualize = Signal(str, str)   # (type: "curve"|"series", id)
    send_to_process   = Signal(str, str)   # (type, id)
    project_modified  = Signal()
    tree_filter_kinds = ["folder", "source_file", "data_file", "image_work", "series", "curve", "analysis_result"]

    @property
    def _selected_type(self):
        return self._workspace_state.selected_type

    @_selected_type.setter
    def _selected_type(self, value):
        self._workspace_state.selected_type = value

    @property
    def _selected_id(self):
        return self._workspace_state.selected_id

    @_selected_id.setter
    def _selected_id(self, value):
        self._workspace_state.selected_id = value

    @property
    def _selected_node_kind(self):
        return self._workspace_state.selected_node_kind

    @_selected_node_kind.setter
    def _selected_node_kind(self, value):
        self._workspace_state.selected_node_kind = value

    @property
    def _selected_node_id(self):
        return self._workspace_state.selected_node_id

    @_selected_node_id.setter
    def _selected_node_id(self, value):
        self._workspace_state.selected_node_id = value

    @property
    def _preview_xs(self):
        return self._workspace_state.preview_xs

    @_preview_xs.setter
    def _preview_xs(self, value):
        self._workspace_state.preview_xs = value

    @property
    def _preview_ys(self):
        return self._workspace_state.preview_ys

    @_preview_ys.setter
    def _preview_ys(self, value):
        self._workspace_state.preview_ys = value

    @property
    def _preview_name(self):
        return self._workspace_state.preview_name

    @_preview_name.setter
    def _preview_name(self, value):
        self._workspace_state.preview_name = value

    @property
    def _preview_x_label(self):
        return self._workspace_state.preview_x_label

    @_preview_x_label.setter
    def _preview_x_label(self, value):
        self._workspace_state.preview_x_label = value

    @property
    def _preview_y_label(self):
        return self._workspace_state.preview_y_label

    @_preview_y_label.setter
    def _preview_y_label(self, value):
        self._workspace_state.preview_y_label = value

    @property
    def _pending_import_paths(self):
        return self._workspace_state.pending_import_paths

    @_pending_import_paths.setter
    def _pending_import_paths(self, value):
        self._workspace_state.pending_import_paths = value

    @property
    def _pending_import_names(self):
        return self._workspace_state.pending_import_names

    @_pending_import_names.setter
    def _pending_import_names(self, value):
        self._workspace_state.pending_import_names = value

    @property
    def _node_preview_states(self):
        return self._workspace_state.node_preview_states

    @_node_preview_states.setter
    def _node_preview_states(self, value):
        self._workspace_state.node_preview_states = value

    @property
    def _current_extension_config_id(self):
        return self._workspace_state.current_extension_config_id

    @_current_extension_config_id.setter
    def _current_extension_config_id(self, value):
        self._workspace_state.current_extension_config_id = value

    @property
    def _pending_import_states(self):
        return self._page_state_bridge.pending_import_states

    @_pending_import_states.setter
    def _pending_import_states(self, value):
        self._page_state_bridge.pending_import_states = value

    @property
    def _external_browser_dir(self):
        return self._page_state_bridge.external_browser_dir

    @_external_browser_dir.setter
    def _external_browser_dir(self, value):
        self._page_state_bridge.external_browser_dir = value

    @property
    def _show_hidden_browser_entries(self):
        return self._page_state_bridge.show_hidden_browser_entries

    @_show_hidden_browser_entries.setter
    def _show_hidden_browser_entries(self, value):
        self._page_state_bridge.show_hidden_browser_entries = value

    @property
    def _data_file_preview_node_id(self):
        return self._page_state_bridge.data_file_preview_node_id

    @_data_file_preview_node_id.setter
    def _data_file_preview_node_id(self, value):
        self._page_state_bridge.data_file_preview_node_id = value

    @property
    def _preview_image_path(self):
        return self._page_state_bridge.preview_image_path

    @_preview_image_path.setter
    def _preview_image_path(self, value):
        self._page_state_bridge.preview_image_path = value

    @property
    def _current_source_preview_total_rows(self):
        return self._page_state_bridge.current_source_preview_total_rows

    @_current_source_preview_total_rows.setter
    def _current_source_preview_total_rows(self, value):
        self._page_state_bridge.current_source_preview_total_rows = value

    @property
    def _fluent_tooltip(self):
        return self._page_state_bridge.fluent_tooltip

    @_fluent_tooltip.setter
    def _fluent_tooltip(self, value):
        self._page_state_bridge.fluent_tooltip = value

    @property
    def _fluent_tooltip_views(self):
        return self._page_state_bridge.fluent_tooltip_views

    @_fluent_tooltip_views.setter
    def _fluent_tooltip_views(self, value):
        self._page_state_bridge.fluent_tooltip_views = value

    @property
    def _shortcut_bindings(self):
        return self._page_state_bridge.shortcut_bindings

    @_shortcut_bindings.setter
    def _shortcut_bindings(self, value):
        self._page_state_bridge.shortcut_bindings = value

    def __init__(self, parent=None):
        super().__init__(parent)
        # 共享树/预览状态走 DataWorkspaceState，DataPage 自身只保留页面装配状态。
        self._workspace_state = DataWorkspaceState()
        self._workspace_controller = DataWorkspaceController(self._workspace_state)
        self._page_state_bridge = DataPageStateBridge()
        self._preview_editor_kind: str | None = None
        self._preview_editor_node_id: str | None = None
        self._preview_editor_original_text: str = ""
        self._pending_import_states = {
            "source_files": _PendingImportQueueState(),
            "datasets": _PendingImportQueueState(),
            "images": _PendingImportQueueState(),
        }
        self._source_favorite_paths: list[str] = get_data_page_source_favorites()
        self._external_browser_dir = None
        self._show_hidden_browser_entries = False
        self._data_file_preview_node_id = None
        self._preview_image_path = None
        self._current_source_preview_total_rows = 0
        self._fluent_tooltip = None
        self._fluent_tooltip_views = {}
        self._theme_refresh_pending = False
        self._shortcut_bindings = ShortcutBindingSet()
        self._setup_ui()
        self._setup_shortcuts()
        self._click_away_focus_commit = install_click_away_focus_commit(self)
        self._onboarding_controller = PageOnboardingController(self, "data", self._data_onboarding_steps)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._theme_refresh_pending:
            self._theme_refresh_pending = False
            QTimer.singleShot(0, self._draw_preview)
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
        item_tooltip_views = getattr(self, "_fluent_tooltip_views", {})
        if watched in item_tooltip_views:
            if event.type() == QEvent.Type.ToolTip:
                self._show_fluent_tooltip_for_item_view(item_tooltip_views[watched], event)
                return True
            if event.type() in {
                QEvent.Type.Leave,
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseButtonDblClick,
            }:
                self._hide_fluent_tooltip()
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

    def _dialog_parent(self) -> QWidget:
        window = self.window()
        return window if isinstance(window, QWidget) else self

    def _install_item_view_tooltip_filter(self, view: TreeWidget) -> None:
        viewport = view.viewport()
        self._fluent_tooltip_views[viewport] = view
        viewport.installEventFilter(self)

    def _sync_plot_preview_toolbar_visibility(self, *_args) -> None:
        if not hasattr(self, "_plot_preview_toolbar_widget") or not hasattr(self, "_preview_stack"):
            return
        visible = self._preview_stack.currentWidget() is getattr(self, "_plot_preview_panel", None)
        self._plot_preview_toolbar_widget.setVisible(bool(visible))

    @staticmethod
    def _tooltip_item_at_event(view: TreeWidget, event) -> Optional[QTreeWidgetItem]:
        if hasattr(event, "position"):
            return view.itemAt(event.position().toPoint())
        if hasattr(event, "pos"):
            return view.itemAt(event.pos())
        return None

    @staticmethod
    def _tooltip_global_pos(view: TreeWidget, event) -> QPoint:
        viewport = view.viewport()
        if hasattr(event, "globalPos"):
            return event.globalPos()
        if hasattr(event, "position"):
            return viewport.mapToGlobal(event.position().toPoint())
        if hasattr(event, "pos"):
            return viewport.mapToGlobal(event.pos())
        return viewport.mapToGlobal(viewport.rect().center())

    def _show_fluent_tooltip_for_item_view(self, view: TreeWidget, event) -> None:
        item = self._tooltip_item_at_event(view, event)
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
        self._fluent_tooltip.move(self._tooltip_global_pos(view, event) + QPoint(12, 18))
        self._fluent_tooltip.show()

    def _hide_fluent_tooltip(self) -> None:
        if self._fluent_tooltip is not None:
            self._fluent_tooltip.hide()

    def _install_preview_drop_targets(self) -> None:
        targets = [
            self._preview_stack,
            self._plot_preview_panel,
            self._image_preview_label,
            self._text_preview,
            self._parsed_preview_table,
        ]
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
        bg = preview_canvas_background_color(dark)
        fg = preview_canvas_foreground_color(dark)
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
        self._parsed_preview_table.setStyleSheet(
            self._parsed_preview_table.styleSheet()
        )
        self._parsed_preview_table.setBorderVisible(True)
        self._parsed_preview_table.setBorderRadius(12)

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
        self._manage_target_label = _TextActionLabel("[未选择] 节点", panel)
        self._manage_target_label.setWordWrap(True)
        self._manage_target_label.clicked.connect(self._show_current_node_details)
        manage_layout.addWidget(self._manage_target_label)

        self._manage_type_label = CaptionLabel("", panel)
        self._manage_type_label.setWordWrap(True)
        self._manage_type_label.hide()
        manage_layout.addWidget(self._manage_type_label)
        self._apply_manage_target_action_style(False)
        self._apply_muted_summary_label_style(self._manage_type_label)

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
        self._btn_import_source_to_data = PrimaryPushButton(FIF.DOWNLOAD, "导入到数据集", self._source_file_action_panel)
        self._btn_import_source_to_data.clicked.connect(self._import_current_source_file_to_dataset)
        self._btn_import_source_to_digitize = PushButton(FIF.PHOTO, "导入到数字化", self._source_file_action_panel)
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
        self._pending_source_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._pending_source_list.itemSelectionChanged.connect(self._refresh_pending_source_controls)
        self._pending_source_list.customContextMenuRequested.connect(self._show_pending_source_context_menu)
        self._pending_source_list.itemDoubleClicked.connect(self._begin_rename_pending_source_item)
        self._pending_source_list.itemChanged.connect(self._on_pending_source_item_changed)
        self._install_item_view_tooltip_filter(self._pending_source_list)
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
        self._btn_import_pending_default = PushButton("默认模式导入", self._import_queue_panel)
        self._btn_import_pending_default.clicked.connect(self._import_pending_source_files_to_datasets_default_mode)
        self._btn_import_pending = PrimaryPushButton(FIF.DOWNLOAD, "执行导入", self._import_queue_panel)
        self._btn_import_pending.clicked.connect(self._import_pending_files_for_current_group)
        self._apply_panel_button_metrics(self._btn_import_pending_default, self._btn_import_pending)
        import_row.addWidget(self._btn_import_pending_default, 1)
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
        self._preview_layout = preview_layout

        preview_header = QHBoxLayout()
        self._preview_section_label = make_section_label("数据预览")
        preview_header.addWidget(self._preview_section_label)
        preview_header.addStretch()
        self._extension_config_action_panel = QWidget(self._preview_card)
        extension_config_action_layout = QHBoxLayout(self._extension_config_action_panel)
        extension_config_action_layout.setContentsMargins(0, 0, 0, 0)
        extension_config_action_layout.setSpacing(6)
        self._btn_reset_extension_config = PushButton("重置配置", self._extension_config_action_panel)
        self._btn_reset_extension_config.clicked.connect(self._reset_selected_extension_config_edit)
        apply_button_metrics(self._btn_reset_extension_config, min_width=96)
        self._btn_reset_extension_config.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        extension_config_action_layout.addWidget(self._btn_reset_extension_config)
        self._btn_save_extension_config = PrimaryPushButton("保存配置", self._extension_config_action_panel)
        self._btn_save_extension_config.clicked.connect(self._save_selected_extension_config)
        apply_button_metrics(self._btn_save_extension_config, min_width=96)
        self._btn_save_extension_config.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        extension_config_action_layout.addWidget(self._btn_save_extension_config)
        self._extension_config_action_panel.hide()
        self._source_file_preview_controls = QWidget(self._preview_card)
        source_file_preview_layout = QHBoxLayout(self._source_file_preview_controls)
        source_file_preview_layout.setContentsMargins(0, 0, 0, 0)
        source_file_preview_layout.setSpacing(6)
        source_file_preview_layout.addWidget(CaptionLabel("预览", self._preview_card))
        self._source_file_preview_combo = ComboBox(self._preview_card)
        self._source_file_preview_combo.setFixedHeight(WORKBENCH_BUTTON_HEIGHT)
        self._source_file_preview_combo.setMinimumWidth(120)
        self._source_file_preview_combo.currentIndexChanged.connect(self._on_source_file_preview_mode_changed)
        source_file_preview_layout.addWidget(self._source_file_preview_combo)
        preview_header.addWidget(self._source_file_preview_controls)
        self._preview_plot_type_controls = QWidget(self._preview_card)
        preview_plot_type_layout = QHBoxLayout(self._preview_plot_type_controls)
        preview_plot_type_layout.setContentsMargins(0, 0, 0, 0)
        preview_plot_type_layout.setSpacing(6)
        preview_plot_type_layout.addWidget(CaptionLabel("图型", self._preview_card))
        self._preview_type_combo = ComboBox(self._preview_card)
        self._preview_type_combo.setFixedHeight(WORKBENCH_BUTTON_HEIGHT)
        self._preview_type_combo.setMinimumWidth(120)
        self._preview_type_combo.addItems(["折线", "散点", "折线+点", "柱状", "阶梯"])
        self._preview_type_combo.currentIndexChanged.connect(self._on_preview_plot_type_changed)
        preview_plot_type_layout.addWidget(self._preview_type_combo)
        preview_header.addWidget(self._preview_plot_type_controls)
        preview_layout.addLayout(preview_header)

        self._config_editor_header_panel = QWidget(self._preview_card)
        config_editor_header_layout = QVBoxLayout(self._config_editor_header_panel)
        config_editor_header_layout.setContentsMargins(0, 0, 0, 0)
        config_editor_header_layout.setSpacing(4)

        self._config_editor_title_label = BodyLabel("", self._config_editor_header_panel)
        self._config_editor_title_label.setWordWrap(True)
        self._config_editor_title_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._apply_summary_label_style(self._config_editor_title_label)
        config_editor_header_layout.addWidget(self._config_editor_title_label)

        self._config_editor_meta_label = CaptionLabel("", self._config_editor_header_panel)
        self._config_editor_meta_label.setWordWrap(True)
        self._config_editor_meta_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._apply_muted_summary_label_style(self._config_editor_meta_label)
        config_editor_header_layout.addWidget(self._config_editor_meta_label)

        self._config_editor_header_panel.hide()
        preview_layout.addWidget(self._config_editor_header_panel)

        self._source_file_detail_controls = QWidget(self._preview_card)
        source_file_detail_layout = QHBoxLayout(self._source_file_detail_controls)
        source_file_detail_layout.setContentsMargins(0, 0, 0, 0)
        source_file_detail_layout.setSpacing(6)
        self._source_file_sheet_label = CaptionLabel("工作表", self._preview_card)
        source_file_detail_layout.addWidget(self._source_file_sheet_label)
        self._source_file_sheet_combo = ComboBox(self._preview_card)
        self._source_file_sheet_combo.setFixedHeight(WORKBENCH_BUTTON_HEIGHT)
        self._source_file_sheet_combo.setMinimumWidth(140)
        self._source_file_sheet_combo.currentIndexChanged.connect(self._on_source_file_sheet_changed)
        source_file_detail_layout.addWidget(self._source_file_sheet_combo)
        source_file_detail_layout.addWidget(CaptionLabel("显示行数", self._preview_card))
        self._source_file_row_limit_edit = LineEdit(self._preview_card)
        self._source_file_row_limit_edit.setFixedHeight(WORKBENCH_BUTTON_HEIGHT)
        self._source_file_row_limit_edit.setFixedWidth(84)
        self._source_file_row_limit_edit.setPlaceholderText("80")
        self._source_file_row_limit_edit.setText("80")
        self._source_file_row_limit_edit.setValidator(QIntValidator(1, 2000, self._source_file_row_limit_edit))
        self._source_file_row_limit_edit.editingFinished.connect(self._on_source_file_row_limit_changed)
        source_file_detail_layout.addWidget(self._source_file_row_limit_edit)
        self._source_file_skip_rows_label = CaptionLabel("跳过行数", self._preview_card)
        source_file_detail_layout.addWidget(self._source_file_skip_rows_label)
        self._source_file_skip_rows_edit = LineEdit(self._preview_card)
        self._source_file_skip_rows_edit.setFixedHeight(WORKBENCH_BUTTON_HEIGHT)
        self._source_file_skip_rows_edit.setFixedWidth(84)
        self._source_file_skip_rows_edit.setPlaceholderText("0")
        self._source_file_skip_rows_edit.setText("0")
        self._source_file_skip_rows_edit.setValidator(QIntValidator(0, 999999, self._source_file_skip_rows_edit))
        self._source_file_skip_rows_edit.editingFinished.connect(self._on_source_file_skip_rows_changed)
        source_file_detail_layout.addWidget(self._source_file_skip_rows_edit)
        self._source_file_first_page_btn = ToolButton(FIF.LEFT_ARROW, self._preview_card)
        self._source_file_first_page_btn.clicked.connect(self._show_first_source_file_page)
        self._source_file_first_page_btn.installEventFilter(ToolTipFilter(self._source_file_first_page_btn, 300, ToolTipPosition.TOP))
        self._source_file_first_page_btn.setToolTip("首页")
        source_file_detail_layout.addWidget(self._source_file_first_page_btn)
        self._source_file_prev_page_btn = PushButton("上一页", self._preview_card)
        self._source_file_next_page_btn = PushButton("下一页", self._preview_card)
        apply_button_metrics(self._source_file_prev_page_btn, self._source_file_next_page_btn, min_width=72)
        self._source_file_prev_page_btn.clicked.connect(self._show_previous_source_file_page)
        self._source_file_next_page_btn.clicked.connect(self._show_next_source_file_page)
        source_file_detail_layout.addWidget(self._source_file_prev_page_btn)
        self._source_file_jump_line_edit = LineEdit(self._preview_card)
        self._source_file_jump_line_edit.setFixedHeight(WORKBENCH_BUTTON_HEIGHT)
        self._source_file_jump_line_edit.setFixedWidth(92)
        self._source_file_jump_line_edit.setPlaceholderText("跳转行")
        self._source_file_jump_line_edit.setValidator(QIntValidator(1, 999999999, self._source_file_jump_line_edit))
        self._source_file_jump_line_edit.editingFinished.connect(self._jump_to_source_file_page)
        source_file_detail_layout.addWidget(self._source_file_jump_line_edit)
        source_file_detail_layout.addWidget(self._source_file_next_page_btn)
        self._source_file_last_page_btn = ToolButton(FIF.RIGHT_ARROW, self._preview_card)
        self._source_file_last_page_btn.clicked.connect(self._show_last_source_file_page)
        self._source_file_last_page_btn.installEventFilter(ToolTipFilter(self._source_file_last_page_btn, 300, ToolTipPosition.TOP))
        self._source_file_last_page_btn.setToolTip("尾页")
        source_file_detail_layout.addWidget(self._source_file_last_page_btn)
        self._source_file_page_label = CaptionLabel("0 - 0 / 0", self._preview_card)
        self._source_file_page_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        source_file_detail_layout.addWidget(self._source_file_page_label)
        source_file_detail_layout.addStretch()
        preview_layout.addWidget(self._source_file_detail_controls)

        self._extension_preview_panel = QWidget(self._preview_card)
        extension_preview_layout = QVBoxLayout(self._extension_preview_panel)
        extension_preview_layout.setContentsMargins(0, 0, 0, 0)
        extension_preview_layout.setSpacing(6)

        self._extension_detail_label = BodyLabel("", self._extension_preview_panel)
        self._extension_detail_label.setWordWrap(True)
        self._extension_detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._apply_summary_label_style(self._extension_detail_label)
        extension_preview_layout.addWidget(self._extension_detail_label)

        self._extension_detail_meta_label = CaptionLabel("", self._extension_preview_panel)
        self._extension_detail_meta_label.setWordWrap(True)
        self._extension_detail_meta_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._apply_muted_summary_label_style(self._extension_detail_meta_label)
        extension_preview_layout.addWidget(self._extension_detail_meta_label)

        self._extension_field_help_title = BodyLabel("参数说明", self._extension_preview_panel)
        self._apply_summary_label_style(self._extension_field_help_title)
        extension_preview_layout.addWidget(self._extension_field_help_title)

        self._extension_field_help_area = SmoothScrollArea(self._extension_preview_panel)
        self._extension_field_help_area.setWidgetResizable(True)
        self._extension_field_help_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._extension_field_help_area.setMinimumHeight(_EXTENSION_FIELD_HELP_COMPACT_HEIGHT)
        self._extension_field_help_area.setMaximumHeight(_EXTENSION_FIELD_HELP_COMPACT_HEIGHT)
        self._extension_field_help_area.setStyleSheet("background: transparent; border: none;")
        self._extension_field_help_container = QWidget(self._extension_field_help_area)
        extension_help_layout = QVBoxLayout(self._extension_field_help_container)
        extension_help_layout.setContentsMargins(0, 0, 0, 0)
        extension_help_layout.setSpacing(0)
        self._extension_field_help_label = CaptionLabel("", self._extension_field_help_container)
        self._extension_field_help_label.setWordWrap(True)
        self._extension_field_help_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._apply_muted_summary_label_style(self._extension_field_help_label)
        extension_help_layout.addWidget(self._extension_field_help_label)
        extension_help_layout.addStretch(1)
        self._extension_field_help_area.setWidget(self._extension_field_help_container)
        extension_preview_layout.addWidget(self._extension_field_help_area)

        self._extension_preview_divider = make_hsep(self._extension_preview_panel)
        extension_preview_layout.addWidget(self._extension_preview_divider)

        self._extension_preview_panel.hide()
        preview_layout.addWidget(self._extension_preview_panel)

        self._plot_preview_toolbar_widget = QWidget(self._preview_card)
        preview_toolbar_layout = QVBoxLayout(self._plot_preview_toolbar_widget)
        preview_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        preview_toolbar_layout.setSpacing(0)

        self._plot_preview_panel = QWidget(self._preview_card)
        plot_preview_layout = QVBoxLayout(self._plot_preview_panel)
        plot_preview_layout.setContentsMargins(0, 0, 0, 0)
        plot_preview_layout.setSpacing(0)

        if HAS_MATPLOTLIB:
            self._preview_figure = Figure(figsize=(5.6, 3.4), dpi=100)
            self._preview_canvas = FigureCanvas(self._preview_figure)
            self._preview_nav_toolbar = create_navigation_toolbar(
                self._preview_canvas,
                self._plot_preview_panel,
                sync_callback=self._sync_preview_nav_toggle_states,
            )
            preview_toolbar, preview_buttons = build_preview_toolbar(
                self._plot_preview_toolbar_widget,
                button_size=WORKBENCH_BUTTON_HEIGHT,
                reset_callback=self._reset_preview_view,
                zoom_in_callback=lambda: self._zoom_preview_axes(0.8),
                zoom_out_callback=lambda: self._zoom_preview_axes(1.25),
                pan_toggle_callback=self._toggle_preview_pan_mode,
                box_zoom_toggle_callback=self._toggle_preview_box_zoom_mode,
            )
            self._preview_fit_btn = preview_buttons.fit
            self._preview_zoom_in_btn = preview_buttons.zoom_in
            self._preview_zoom_out_btn = preview_buttons.zoom_out
            self._preview_pan_btn = preview_buttons.pan
            self._preview_box_zoom_btn = preview_buttons.box_zoom
            preview_toolbar_layout.addLayout(preview_toolbar)
            plot_preview_layout.addWidget(self._preview_canvas, stretch=1)
            self._sync_preview_nav_toggle_states()
        else:
            self._preview_figure = None
            self._preview_canvas = None
            self._preview_nav_toolbar = None
            self._plot_preview_toolbar_widget.hide()
            self._preview_canvas_label = BodyLabel(
                f"matplotlib 加载失败：{_MATPLOTLIB_ERROR}" if _MATPLOTLIB_ERROR else "请安装 matplotlib 以启用绘图预览",
                self._preview_card,
            )
            self._preview_canvas_label.setWordWrap(True)
            self._preview_canvas_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            plot_preview_layout.addWidget(self._preview_canvas_label, stretch=1)

        preview_layout.addWidget(self._plot_preview_toolbar_widget)
        self._preview_stack = QStackedWidget(self._preview_card)
        preview_layout.addWidget(self._preview_stack, stretch=3)
        self._preview_stack.addWidget(self._plot_preview_panel)
        self._preview_stack.currentChanged.connect(self._sync_plot_preview_toolbar_visibility)
        self._sync_plot_preview_toolbar_visibility()

        self._image_preview_label = QLabel(self._preview_card)
        self._image_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_preview_label.setMinimumHeight(240)
        self._image_preview_label.setWordWrap(True)
        self._preview_stack.addWidget(self._image_preview_label)

        self._picture_preview_tree = TreeWidget(self._preview_card)
        self._picture_preview_tree.setHeaderHidden(True)
        self._picture_preview_tree.setMinimumHeight(240)
        self._picture_preview_tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._install_item_view_tooltip_filter(self._picture_preview_tree)
        self._preview_stack.addWidget(self._picture_preview_tree)

        self._text_preview = PlainTextEdit(self._preview_card)
        self._text_preview.setReadOnly(True)
        self._text_preview.setMinimumHeight(240)
        self._preview_stack.addWidget(self._text_preview)

        self._parsed_preview_table = TableWidget(self._preview_card)
        self._parsed_preview_table.setMinimumHeight(240)
        self._parsed_preview_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._parsed_preview_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._parsed_preview_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._parsed_preview_table.setAlternatingRowColors(True)
        self._parsed_preview_table.verticalHeader().setVisible(False)
        self._parsed_preview_table.horizontalHeader().setHighlightSections(False)
        self._parsed_preview_table.setWordWrap(False)
        self._parsed_preview_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._preview_stack.addWidget(self._parsed_preview_table)

        self._preview_summary_divider = make_hsep()
        preview_layout.addWidget(self._preview_summary_divider)

        self._summary_footer = QWidget(self._preview_card)
        summary_footer_layout = QVBoxLayout(self._summary_footer)
        summary_footer_layout.setContentsMargins(0, 0, 0, 0)
        summary_footer_layout.setSpacing(4)

        self._stats_title_label = BodyLabel("（选择数据后显示统计信息）", self._summary_footer)
        self._stats_title_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._apply_summary_label_style(self._stats_title_label)
        summary_footer_layout.addWidget(self._stats_title_label)

        self._stats_label = CaptionLabel("", self._summary_footer)
        self._stats_label.setWordWrap(True)
        self._stats_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._apply_muted_summary_label_style(self._stats_label)
        summary_footer_layout.addWidget(self._stats_label)

        self._source_path_panel = QWidget(self._summary_footer)
        source_path_layout = QVBoxLayout(self._source_path_panel)
        source_path_layout.setContentsMargins(0, 0, 0, 0)
        source_path_layout.setSpacing(4)

        current_path_row = QHBoxLayout()
        current_path_row.setContentsMargins(0, 0, 0, 0)
        self._current_source_path_prefix = CaptionLabel("当前路径:", self._source_path_panel)
        self._apply_muted_summary_label_style(self._current_source_path_prefix)
        current_path_row.addWidget(self._current_source_path_prefix)
        self._current_source_path_button = self._create_path_link_button(self._source_path_panel)
        current_path_row.addWidget(self._current_source_path_button, 0)
        current_path_row.addStretch(1)
        source_path_layout.addLayout(current_path_row)

        origin_path_row = QHBoxLayout()
        origin_path_row.setContentsMargins(0, 0, 0, 0)
        self._origin_source_path_prefix = CaptionLabel("源路径:", self._source_path_panel)
        self._apply_muted_summary_label_style(self._origin_source_path_prefix)
        origin_path_row.addWidget(self._origin_source_path_prefix)
        self._origin_source_path_button = self._create_path_link_button(self._source_path_panel)
        origin_path_row.addWidget(self._origin_source_path_button, 0)
        origin_path_row.addStretch(1)
        source_path_layout.addLayout(origin_path_row)

        summary_footer_layout.addWidget(self._source_path_panel)
        preview_layout.addWidget(self._summary_footer)
        preview_layout.addWidget(self._extension_config_action_panel)

        self._source_manager_card = self._build_source_manager_card(panel)
        self._right_mode_stack.addWidget(self._preview_card)
        self._right_mode_stack.addWidget(self._source_manager_card)
        self._extension_config_original_text = "{}"
        self._set_actions_enabled(False)
        self._set_source_file_preview_mode_controls_visible(False)
        self._set_source_file_detail_controls_visible(False)
        self._set_preview_plot_type_controls_visible(False)
        self._set_source_path_links_visible(False)
        return panel

    def _set_preview_plot_type_controls_visible(self, visible: bool) -> None:
        self._preview_plot_type_controls.setVisible(visible)

    def _set_source_file_preview_mode_controls_visible(self, visible: bool) -> None:
        self._source_file_preview_controls.setVisible(visible)

    def _set_source_file_detail_controls_visible(self, visible: bool) -> None:
        self._source_file_detail_controls.setVisible(visible)

    def _set_source_file_sheet_controls_visible(self, visible: bool) -> None:
        self._source_file_sheet_label.setVisible(visible)
        self._source_file_sheet_combo.setVisible(visible)

    def _set_source_file_skip_rows_enabled(self, enabled: bool) -> None:
        self._source_file_skip_rows_label.setEnabled(enabled)
        self._source_file_skip_rows_edit.setEnabled(enabled)

    def _set_extension_preview_help(self, description: Optional[dict[str, str]] = None, field_help: str = "") -> None:
        info = dict(description or {}) if isinstance(description, dict) else {}
        title_text = str(info.get("title") or "").strip()
        meta_text = str(info.get("meta") or "").strip()
        field_help_text = str(field_help or "").strip()
        self._extension_detail_label.setText(title_text)
        self._extension_detail_meta_label.setText(meta_text)
        self._extension_field_help_label.setText(field_help_text)
        self._extension_detail_label.setVisible(bool(title_text))
        self._extension_detail_meta_label.setVisible(bool(meta_text))
        self._extension_field_help_title.setVisible(bool(field_help_text))
        self._extension_field_help_area.setVisible(bool(field_help_text))
        self._extension_preview_divider.setVisible(bool(field_help_text))
        self._extension_preview_panel.setVisible(bool(title_text or meta_text or field_help_text))

    def _set_preview_footer_visible(self, visible: bool) -> None:
        self._preview_summary_divider.setVisible(bool(visible))
        self._summary_footer.setVisible(bool(visible))

    def _set_preview_text_editor_mode(
        self,
        enabled: bool,
        *,
        section_label: str = "数据预览",
        action_title: str = "配置编辑",
        reset_text: str = "重置配置",
        save_text: str = "保存配置",
        summary_title: str = "",
        summary_meta: str = "",
    ) -> None:
        if not enabled:
            self._preview_editor_kind = None
            self._preview_editor_node_id = None
            self._preview_editor_original_text = ""
            self._set_preview_footer_visible(True)
            self._extension_config_action_panel.setVisible(False)
            self._config_editor_header_panel.setVisible(False)
            self._text_preview.setReadOnly(True)
            self._preview_section_label.setText(section_label)
            return
        self._preview_section_label.setText(section_label)
        self._extension_config_action_panel.setVisible(True)
        self._config_editor_header_panel.setVisible(True)
        self._set_preview_footer_visible(False)
        self._text_preview.setReadOnly(False)
        self._btn_reset_extension_config.setText(reset_text)
        self._btn_save_extension_config.setText(save_text)
        self._config_editor_title_label.setText(summary_title)
        self._config_editor_meta_label.setText(summary_meta)
        self._preview_name = summary_title or self._preview_name

    def _set_extension_config_editor_mode(self, enabled: bool) -> None:
        if not enabled:
            self._current_extension_config_id = None
        else:
            self._preview_editor_kind = None
            self._preview_editor_node_id = None
            self._preview_editor_original_text = ""
        self._set_preview_text_editor_mode(
            enabled,
            section_label="配置编辑" if enabled else "数据预览",
            action_title="配置编辑",
            reset_text="重置配置",
            save_text="保存配置",
        )

    @staticmethod
    def _preview_numeric_input_value(line_edit: LineEdit, *, minimum: int, fallback: int) -> int:
        text = line_edit.text().strip()
        try:
            value = int(text)
        except ValueError:
            value = fallback
        return max(minimum, value)

    @staticmethod
    def _set_preview_numeric_input_value(line_edit: LineEdit, value: int) -> None:
        line_edit.blockSignals(True)
        line_edit.setText(str(value))
        line_edit.blockSignals(False)

    def _set_preview_summary(self, summary_lines: list[str]) -> None:
        normalized_lines = [line.strip() for line in summary_lines if line and line.strip()]
        title = normalized_lines[0] if normalized_lines else "（选择数据后显示统计信息）"
        details = normalized_lines[1:]
        self._stats_title_label.setText(title)
        self._stats_label.setText("  ·  ".join(details) if details else "（暂无更多摘要信息）")

    def _preview_state_for_node(self, node_id: Optional[str]) -> _NodePreviewState:
        if not node_id:
            return _NodePreviewState()
        return self._node_preview_states.setdefault(node_id, _NodePreviewState())

    def _restore_plot_type_for_node(self, node_id: Optional[str]) -> None:
        plot_type = self._preview_state_for_node(node_id).plot_type
        if not plot_type:
            return
        self._preview_type_combo.blockSignals(True)
        try:
            for index in range(self._preview_type_combo.count()):
                if self._preview_type_combo.itemText(index) == plot_type:
                    self._preview_type_combo.setCurrentIndex(index)
                    break
        finally:
            self._preview_type_combo.blockSignals(False)

    def _restore_source_file_detail_state(self, node_id: Optional[str]) -> _NodePreviewState:
        state = self._preview_state_for_node(node_id)
        self._set_preview_numeric_input_value(self._source_file_row_limit_edit, max(1, state.row_limit))
        self._set_preview_numeric_input_value(self._source_file_skip_rows_edit, max(0, state.skip_rows))
        return state

    def _configure_source_file_sheet_options(self, sheet_names: list[str], preferred_sheet: str = "") -> str:
        options = [sheet for sheet in sheet_names if sheet]
        target_sheet = preferred_sheet if preferred_sheet in options else (options[0] if options else "")
        self._source_file_sheet_combo.blockSignals(True)
        self._source_file_sheet_combo.clear()
        if options:
            self._source_file_sheet_combo.addItems(options)
            self._source_file_sheet_combo.setCurrentIndex(options.index(target_sheet))
        self._source_file_sheet_combo.blockSignals(False)
        self._set_source_file_sheet_controls_visible(bool(options))
        return target_sheet

    def _update_source_file_page_controls(self, total_rows: int, row_offset: int, row_limit: int, *, visible: bool) -> None:
        self._current_source_preview_total_rows = max(0, total_rows)
        self._set_source_file_detail_controls_visible(visible)
        if not visible:
            self._source_file_page_label.setText("0 - 0 / 0")
            self._source_file_first_page_btn.setEnabled(False)
            self._source_file_prev_page_btn.setEnabled(False)
            self._source_file_next_page_btn.setEnabled(False)
            self._source_file_last_page_btn.setEnabled(False)
            self._source_file_jump_line_edit.setEnabled(False)
            return
        if total_rows <= 0:
            start = 0
            end = 0
        else:
            start = row_offset + 1
            end = min(row_offset + row_limit, total_rows)
        self._source_file_page_label.setText(f"{start} - {end} / {total_rows}")
        self._source_file_first_page_btn.setEnabled(row_offset > 0)
        self._source_file_prev_page_btn.setEnabled(row_offset > 0)
        self._source_file_next_page_btn.setEnabled(total_rows > row_offset + row_limit)
        self._source_file_last_page_btn.setEnabled(total_rows > row_offset + row_limit)
        self._source_file_jump_line_edit.setEnabled(total_rows > 0)

    def _on_source_file_preview_mode_changed(self, _index: int) -> None:
        if self._selected_node_kind == "source_file" and self._selected_node_id:
            state = self._preview_state_for_node(self._selected_node_id)
            state.source_preview_mode = self._current_source_file_preview_mode()
            state.row_offset = 0
            self._show_source_file_preview(self._selected_node_id)

    def _on_source_file_sheet_changed(self, _index: int) -> None:
        if self._selected_node_kind == "source_file" and self._selected_node_id:
            state = self._preview_state_for_node(self._selected_node_id)
            state.selected_sheet = self._source_file_sheet_combo.currentText().strip()
            state.row_offset = 0
            self._show_source_file_preview(self._selected_node_id)

    def _on_source_file_row_limit_changed(self) -> None:
        if self._selected_node_kind == "source_file" and self._selected_node_id:
            state = self._preview_state_for_node(self._selected_node_id)
            value = self._preview_numeric_input_value(
                self._source_file_row_limit_edit,
                minimum=1,
                fallback=max(1, state.row_limit),
            )
            self._set_preview_numeric_input_value(self._source_file_row_limit_edit, value)
            state.row_limit = value
            state.row_offset = 0
            self._show_source_file_preview(self._selected_node_id)

    def _on_source_file_skip_rows_changed(self) -> None:
        if self._selected_node_kind == "source_file" and self._selected_node_id:
            state = self._preview_state_for_node(self._selected_node_id)
            value = self._preview_numeric_input_value(
                self._source_file_skip_rows_edit,
                minimum=0,
                fallback=max(0, state.skip_rows),
            )
            self._set_preview_numeric_input_value(self._source_file_skip_rows_edit, value)
            state.skip_rows = value
            state.row_offset = 0
            self._show_source_file_preview(self._selected_node_id)

    def _show_previous_source_file_page(self) -> None:
        if self._selected_node_kind != "source_file" or not self._selected_node_id:
            return
        state = self._preview_state_for_node(self._selected_node_id)
        state.row_offset = max(0, state.row_offset - max(1, state.row_limit))
        self._show_source_file_preview(self._selected_node_id)

    def _show_first_source_file_page(self) -> None:
        if self._selected_node_kind != "source_file" or not self._selected_node_id:
            return
        state = self._preview_state_for_node(self._selected_node_id)
        state.row_offset = 0
        self._show_source_file_preview(self._selected_node_id)

    def _show_next_source_file_page(self) -> None:
        if self._selected_node_kind != "source_file" or not self._selected_node_id:
            return
        state = self._preview_state_for_node(self._selected_node_id)
        if self._current_source_preview_total_rows <= 0:
            return
        next_offset = state.row_offset + max(1, state.row_limit)
        if next_offset >= self._current_source_preview_total_rows:
            return
        state.row_offset = next_offset
        self._show_source_file_preview(self._selected_node_id)

    def _show_last_source_file_page(self) -> None:
        if self._selected_node_kind != "source_file" or not self._selected_node_id:
            return
        state = self._preview_state_for_node(self._selected_node_id)
        if self._current_source_preview_total_rows <= 0:
            return
        page_size = max(1, state.row_limit)
        state.row_offset = ((self._current_source_preview_total_rows - 1) // page_size) * page_size
        self._show_source_file_preview(self._selected_node_id)

    def _jump_to_source_file_page(self) -> None:
        if self._selected_node_kind != "source_file" or not self._selected_node_id:
            return
        if self._current_source_preview_total_rows <= 0:
            return
        state = self._preview_state_for_node(self._selected_node_id)
        target_line = self._preview_numeric_input_value(
            self._source_file_jump_line_edit,
            minimum=1,
            fallback=1,
        )
        target_line = min(target_line, self._current_source_preview_total_rows)
        self._set_preview_numeric_input_value(self._source_file_jump_line_edit, target_line)
        page_size = max(1, state.row_limit)
        state.row_offset = ((target_line - 1) // page_size) * page_size
        self._show_source_file_preview(self._selected_node_id)

    def _configure_source_file_preview_modes(self, file_path: str, preferred_mode: str = "解析") -> None:
        options = ["解析", "源文件"] if self._supports_dataset_import(file_path) else ["源文件"]
        self._source_file_preview_combo.blockSignals(True)
        self._source_file_preview_combo.clear()
        self._source_file_preview_combo.addItems(options)
        target_mode = preferred_mode if preferred_mode in options else ("解析" if "解析" in options else options[0])
        self._source_file_preview_combo.setCurrentIndex(options.index(target_mode))
        self._source_file_preview_combo.blockSignals(False)
        self._set_source_file_preview_mode_controls_visible(len(options) > 1)
        self._set_source_file_skip_rows_enabled(target_mode == "解析")

    def _current_source_file_preview_mode(self) -> str:
        mode = self._source_file_preview_combo.currentText().strip()
        return mode or "解析"

    def _on_preview_plot_type_changed(self, _index: int) -> None:
        if self._selected_node_id:
            self._preview_state_for_node(self._selected_node_id).plot_type = self._preview_type_combo.currentText().strip() or "折线"
        self._draw_preview()

    def _remember_current_external_browser_dir(self) -> None:
        if self._selected_node_kind != "folder" or not self._selected_node_id or self._external_browser_dir is None:
            return
        self._preview_state_for_node(self._selected_node_id).external_browser_dir = str(self._external_browser_dir)

    def _restore_external_browser_dir_for_node(self, node_id: Optional[str]) -> None:
        state = self._preview_state_for_node(node_id)
        if not state.external_browser_dir:
            return
        candidate = Path(state.external_browser_dir)
        if candidate.exists() and candidate.is_dir():
            self._external_browser_dir = candidate

    def _preview_image_target_size(self) -> tuple[int, int]:
        rect = self._image_preview_label.contentsRect()
        width = rect.width()
        height = rect.height()
        if width <= 0 or height <= 0:
            width = self._image_preview_label.width()
            height = self._image_preview_label.height()
        if width <= 0 or height <= 0:
            width = self._preview_stack.width()
            height = self._preview_stack.height()
        return max(width, 320), max(height, 240)

    def _scaled_preview_image_pixmap(self, pixmap: QPixmap) -> QPixmap:
        if pixmap.isNull():
            return pixmap
        target_width, target_height = self._preview_image_target_size()
        return pixmap.scaled(
            target_width,
            target_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _update_preview_image_from_path(self, image_path: str) -> bool:
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            self._preview_image_path = None
            self._image_preview_label.setPixmap(QPixmap())
            return False
        self._preview_image_path = image_path
        self._image_preview_label.setPixmap(self._scaled_preview_image_pixmap(pixmap))
        self._image_preview_label.setText("")
        return True

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

        self._source_browser_tabs = SegmentedStackWidget(card, fill_width=True)
        self._source_browser_tabs.tabBar.setAddButtonVisible(False)
        self._source_browser_tabs.tabBar.setCloseButtonDisplayMode(TabCloseButtonDisplayMode.NEVER)
        self._source_browser_tabs.currentChanged.connect(self._refresh_source_manager_tab_state)

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
        self._install_item_view_tooltip_filter(self._project_source_browser)
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

        self._source_browser_splitter = QSplitter(Qt.Orientation.Horizontal, system_page)
        self._source_browser_splitter.setContentsMargins(0, 0, 0, 0)
        self._source_browser_splitter.setHandleWidth(2)
        self._source_browser_splitter.setChildrenCollapsible(False)
        self._source_browser_splitter.setStyleSheet(
            "QSplitter::handle {"
            "background: transparent;"
            f"border-left: 1px solid {border_color()};"
            "margin: 6px 0;"
            "}"
        )

        self._source_favorites_panel = QWidget(system_page)
        self._source_favorites_panel.setMinimumWidth(120)
        favorites_layout = QVBoxLayout(self._source_favorites_panel)
        favorites_layout.setContentsMargins(0, 0, 0, 0)
        favorites_layout.setSpacing(6)
        favorites_header = QHBoxLayout()
        favorites_header.setContentsMargins(0, 0, 0, 0)
        favorites_header.setSpacing(0)
        self._source_favorites_icon = ToolButton(FIF.HEART, self._source_favorites_panel)
        self._source_favorites_icon.setEnabled(False)
        self._source_favorites_icon.setToolTip("收藏夹")
        self._source_favorites_icon.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)
        favorites_header.addWidget(self._source_favorites_icon)
        favorites_header.addStretch(1)
        favorites_layout.addLayout(favorites_header)
        self._source_favorites_list = TreeWidget(self._source_favorites_panel)
        self._source_favorites_list.setHeaderHidden(True)
        self._source_favorites_list.setMinimumHeight(220)
        self._source_favorites_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._source_favorites_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._source_favorites_list.itemDoubleClicked.connect(self._on_source_favorite_item_activated)
        self._source_favorites_list.customContextMenuRequested.connect(self._show_source_favorites_context_menu)
        self._install_item_view_tooltip_filter(self._source_favorites_list)
        favorites_layout.addWidget(self._source_favorites_list, 1)
        self._source_browser_splitter.addWidget(self._source_favorites_panel)

        browser_panel = QWidget(system_page)
        browser_layout = QVBoxLayout(browser_panel)
        browser_layout.setContentsMargins(0, 0, 0, 0)
        browser_layout.setSpacing(6)

        self._source_breadcrumb_host = QWidget(browser_panel)
        breadcrumb_layout = QHBoxLayout(self._source_breadcrumb_host)
        breadcrumb_layout.setContentsMargins(4, 0, 0, 0)
        breadcrumb_layout.setSpacing(0)
        self._source_breadcrumb_bar = BreadcrumbBar(system_page)
        self._source_breadcrumb_bar.currentItemChanged.connect(self._on_source_breadcrumb_changed)
        breadcrumb_layout.addWidget(self._source_breadcrumb_bar)
        browser_layout.addWidget(self._source_breadcrumb_host)

        self._source_browser = TreeWidget(system_page)
        self._source_browser.setHeaderHidden(True)
        self._source_browser.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._source_browser.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._source_browser.itemSelectionChanged.connect(self._refresh_source_browser_controls)
        self._source_browser.itemDoubleClicked.connect(self._on_source_browser_item_activated)
        self._source_browser.customContextMenuRequested.connect(self._show_source_browser_context_menu)
        self._install_item_view_tooltip_filter(self._source_browser)
        browser_layout.addWidget(self._source_browser, 1)

        self._source_browser_splitter.addWidget(browser_panel)
        self._source_browser_splitter.setStretchFactor(0, 0)
        self._source_browser_splitter.setStretchFactor(1, 1)
        self._source_browser_splitter.setSizes([160, 560])
        system_layout.addWidget(self._source_browser_splitter, 1)

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

    def _apply_manage_target_action_style(self, enabled: bool) -> None:
        color = accent_color() if enabled else secondary_color()
        hover_color_value = accent_color() if enabled else secondary_color()
        self._manage_target_label.setEnabled(enabled)
        self._manage_target_label.setCursor(
            Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor
        )
        self._manage_target_label.setStyleSheet(
            "QLabel {"
            f"color: {color};"
            "font-size: 11px;"
            f"font-weight: {'500' if enabled else '400'};"
            "}"
            "QLabel:hover {"
            f"color: {hover_color_value};"
            f"text-decoration: {'underline' if enabled else 'none'};"
            "}"
        )

    def _set_extension_field_help_height(self, height: int) -> None:
        self._extension_field_help_area.setMinimumHeight(height)
        self._extension_field_help_area.setMaximumHeight(height)

    def _create_path_link_button(self, parent: QWidget) -> HyperlinkButton:
        button = HyperlinkButton(parent)
        button.setFlat(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedHeight(WORKBENCH_BUTTON_HEIGHT)
        button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        font = button.font()
        font.setPointSize(8)
        font.setWeight(QFont.Weight.Normal)
        button.setFont(font)
        button.setStyleSheet(
            "QPushButton {"
            f"color: {accent_color()};"
            "background: transparent;"
            "border: none;"
            "padding: 0;"
            "text-align: left;"
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

    def _refresh_path_link_button_text(self, button: HyperlinkButton) -> None:
        raw_text = str(button.property("fullText") or "")
        empty_text = str(button.property("emptyText") or "未记录")
        display_text = raw_text or empty_text
        metrics = QFontMetrics(button.font())
        if raw_text:
            available_width = self._path_link_available_width(button)
            display_text = metrics.elidedText(raw_text, Qt.TextElideMode.ElideMiddle, available_width)
        button.setText(display_text)
        button.setFixedWidth(max(metrics.horizontalAdvance(display_text) + 6, 24))

    def _path_link_available_width(self, button: HyperlinkButton) -> int:
        raw_text = str(button.property("fullText") or "")
        metrics = QFontMetrics(button.font())
        full_text_width = max(metrics.horizontalAdvance(raw_text) + 6, 24)
        panel_width = self._source_path_panel.width() if hasattr(self, "_source_path_panel") else 0
        if panel_width <= 0:
            return full_text_width

        if button is self._current_source_path_button:
            prefix_width = self._current_source_path_prefix.sizeHint().width()
        else:
            prefix_width = self._origin_source_path_prefix.sizeHint().width()

        return max(panel_width - prefix_width - 24, 24)

    def _refresh_source_path_link_buttons(self) -> None:
        if hasattr(self, "_source_path_panel"):
            layout = self._source_path_panel.layout()
            if layout is not None:
                layout.activate()
        if hasattr(self, "_current_source_path_button"):
            self._refresh_path_link_button_text(self._current_source_path_button)
        if hasattr(self, "_origin_source_path_button"):
            self._refresh_path_link_button_text(self._origin_source_path_button)

    def _open_path_button_target(self, button: HyperlinkButton) -> None:
        self._open_path_in_folder(str(button.property("targetPath") or ""))

    def _set_path_link_button(self, button: HyperlinkButton, file_path: str, empty_text: str = "未记录") -> None:
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
        self._refresh_source_path_link_buttons()

    def _hide_source_path_links(self) -> None:
        self._set_path_link_button(self._current_source_path_button, "", "未记录当前路径")
        self._set_path_link_button(self._origin_source_path_button, "", "未记录源路径")
        self._set_source_path_links_visible(False)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_source_path_link_buttons()
        if self._preview_image_path and self._preview_stack.currentWidget() is self._image_preview_label:
            self._update_preview_image_from_path(self._preview_image_path)

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
        self._remember_current_external_browser_dir()
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

    def _save_source_favorites(self) -> None:
        self._source_favorite_paths = set_data_page_source_favorites(self._source_favorite_paths)

    def _refresh_source_favorites(self) -> None:
        self._source_favorites_list.clear()
        valid_paths: list[str] = []
        for raw_path in self._source_favorite_paths:
            path = Path(raw_path)
            if not path.exists() or not path.is_dir():
                continue
            valid_paths.append(str(path))
            item = QTreeWidgetItem([path.name or str(path)])
            item.setData(0, Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(0, str(path))
            item.setIcon(0, FIF.FOLDER.icon())
            self._source_favorites_list.addTopLevelItem(item)
        self._source_favorite_paths = valid_paths
        self._save_source_favorites()

    def _add_source_favorite(self, dir_path: str) -> bool:
        candidate = Path(str(dir_path or "").strip())
        if not candidate.exists() or not candidate.is_dir():
            return False
        normalized = str(candidate)
        if normalized in self._source_favorite_paths:
            return False
        self._source_favorite_paths.append(normalized)
        self._refresh_source_favorites()
        return True

    def _remove_source_favorite(self, dir_path: str) -> None:
        normalized = str(dir_path or "").strip()
        self._source_favorite_paths = [path for path in self._source_favorite_paths if path != normalized]
        self._refresh_source_favorites()

    def _on_source_favorite_item_activated(self, item, _column: int) -> None:
        if item is None:
            return
        dir_path = str(item.data(0, Qt.ItemDataRole.UserRole) or "").strip()
        if not dir_path:
            return
        candidate = Path(dir_path)
        if not candidate.exists() or not candidate.is_dir():
            self._remove_source_favorite(dir_path)
            return
        self._external_browser_dir = candidate
        self._remember_current_external_browser_dir()
        self._refresh_source_browser()

    def _show_source_favorites_context_menu(self, pos) -> None:
        item = self._source_favorites_list.itemAt(pos)
        if item is None:
            return
        dir_path = str(item.data(0, Qt.ItemDataRole.UserRole) or "").strip()
        if not dir_path:
            return
        menu = RoundMenu(parent=self)
        menu.addAction(Action(FIF.DELETE, "移出收藏夹", self, triggered=lambda: self._remove_source_favorite(dir_path)))
        menu.exec(self._source_favorites_list.viewport().mapToGlobal(pos))

    def _show_source_browser_context_menu(self, pos) -> None:
        item = self._source_browser.itemAt(pos)
        if item is None:
            return
        entry_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if entry_type != "dir":
            return
        dir_path = str(item.data(0, Qt.ItemDataRole.UserRole) or "").strip()
        if not dir_path:
            return
        menu = RoundMenu(parent=self)
        menu.addAction(Action(FIF.ADD, "加入收藏夹", self, triggered=lambda: self._add_source_favorite(dir_path)))
        menu.exec(self._source_browser.viewport().mapToGlobal(pos))
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
        self._set_extension_config_editor_mode(False)
        self._show_preview_mode()
        self._preview_xs = []
        self._preview_ys = []
        self._preview_name = ""
        self._preview_x_label = "X"
        self._preview_y_label = "Y"
        self._data_file_preview_node_id = None
        self._preview_image_path = None
        self._preview_stack.setCurrentWidget(self._plot_preview_panel)
        self._draw_preview()
        self._text_preview.clear()
        self._parsed_preview_table.clear()
        self._parsed_preview_table.setRowCount(0)
        self._parsed_preview_table.setColumnCount(0)
        self._picture_preview_tree.clear()
        self._image_preview_label.clear()
        self._image_preview_label.setText("选择节点后显示预览")
        self._set_preview_summary(["（选择数据后显示统计信息）"])
        self._set_preview_footer_visible(True)
        self._set_source_file_preview_mode_controls_visible(False)
        self._set_source_file_detail_controls_visible(False)
        self._set_source_file_skip_rows_enabled(True)
        self._set_source_file_sheet_controls_visible(False)
        self._source_file_page_label.setText("0 - 0 / 0")
        self._set_preview_plot_type_controls_visible(False)
        self._hide_source_path_links()
        self._set_actions_enabled(False)

    def _set_management_actions_enabled(self, enabled: bool) -> None:
        self._manage_name_edit.setEnabled(enabled)
        self._btn_apply_name.setEnabled(enabled)
        self._btn_delete_node.setEnabled(enabled)

    def _show_preview_mode(self) -> None:
        self._right_mode_stack.setCurrentWidget(self._preview_card)
        self._set_extension_field_help_height(_EXTENSION_FIELD_HELP_COMPACT_HEIGHT)
        self._set_extension_preview_help()
        if not self._extension_config_action_panel.isVisible():
            self._set_preview_footer_visible(True)

    def _show_source_manager_mode(self) -> None:
        self._right_mode_stack.setCurrentWidget(self._source_manager_card)

    def _current_tree_node(self):
        project = project_manager.current_project
        if project is None or project.tree is None or not self._selected_node_id:
            return None
        return project.tree.get_node(self._selected_node_id)

    @classmethod
    def _folder_group_label(cls, group_type: Optional[str]) -> Optional[str]:
        canonical = cls._canonical_folder_group(group_type)
        if canonical is None and group_type:
            canonical = str(group_type)
        return _FOLDER_GROUP_LABELS.get(canonical or "")

    def _current_node_name(self) -> str:
        if not self._selected_node_kind or not self._selected_node_id:
            return ""
        if self._selected_node_kind.startswith("global_"):
            return self._global_preview_node_label(self._selected_node_kind, self._selected_node_id)
        project = project_manager.current_project
        if project is None:
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
        if node is None:
            return ""
        if getattr(node, "kind", None) == "folder":
            return folder_display_name(node) or node.name
        return node.name

    @staticmethod
    def _append_node_detail_section(lines: list[str], title: str) -> None:
        if lines:
            lines.append("")
        lines.append(f"【{title}】")

    @staticmethod
    def _detail_value_text(value: Any) -> Optional[str]:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return "是" if value else "否"
        if isinstance(value, (list, tuple, set)):
            if not value:
                return "0 项"
            if len(value) <= 4 and all(isinstance(item, (str, int, float, bool)) for item in value):
                return "、".join("是" if item is True else "否" if item is False else str(item) for item in value)
            return f"{len(value)} 项"
        if isinstance(value, dict):
            return f"{len(value)} 项"
        return str(value)

    @classmethod
    def _append_node_detail_field(cls, lines: list[str], label: str, value: Any) -> None:
        value_text = cls._detail_value_text(value)
        if value_text is None:
            return
        lines.append(f"{label}: {value_text}")

    @staticmethod
    def _find_series_owner(project, series_id: str) -> tuple[str, Optional[Any]]:
        for data_file in getattr(project, "data_files", []):
            if any(series.id == series_id for series in data_file.series):
                return "data_file", data_file
        for dataset in getattr(project, "datasets", []):
            if any(series.id == series_id for series in dataset.series):
                return "dataset", dataset
        return "", None

    @staticmethod
    def _find_curve_owner_image(project, curve_id: str):
        for image in getattr(project, "images", []):
            if any(curve.id == curve_id for curve in image.curves):
                return image
        return None

    def _current_node_detail_text(self) -> str:
        if not self._selected_node_kind or not self._selected_node_id:
            return ""

        project = project_manager.current_project
        kind = self._selected_node_kind
        node_id = self._selected_node_id
        node = self._current_tree_node()
        lines: list[str] = []

        self._append_node_detail_section(lines, "节点")
        self._append_node_detail_field(lines, "节点类型", self._node_kind_label(kind))
        self._append_node_detail_field(lines, "显示名称", self._current_node_name() or "未命名节点")
        if node is not None:
            self._append_node_detail_field(lines, "树节点 ID", getattr(node, "id", None))
            self._append_node_detail_field(lines, "父节点 ID", getattr(node, "parent_id", None))
            self._append_node_detail_field(lines, "排序", getattr(node, "order", None))
        else:
            self._append_node_detail_field(lines, "标识", node_id)

        if kind == "folder" and node is not None:
            self._append_node_detail_section(lines, "文件夹")
            self._append_node_detail_field(
                lines,
                "分组",
                self._folder_group_label(getattr(node, "group_type", None)) or getattr(node, "group_type", None) or "普通文件夹",
            )
            self._append_node_detail_field(lines, "所在集合", self._folder_group_label(self._folder_collection_group(node)))
            self._append_node_detail_field(lines, "受保护", self._is_protected_folder_node(node))
            if project is not None and project.tree is not None:
                self._append_node_detail_field(lines, "子节点数量", len(project.tree.find_nodes(parent_id=node.id)))
            return "\n".join(lines)

        if project is None:
            return "\n".join(lines)

        if kind == "data_file" and node is not None:
            data_file = project.find_data_file(node.data_file_id)
            if data_file is not None:
                self._append_node_detail_section(lines, "数据文件")
                self._append_node_detail_field(lines, "数据文件 ID", data_file.id)
                self._append_node_detail_field(lines, "导入路径", data_file.source_path)
                self._append_node_detail_field(lines, "导入时间", data_file.import_time)
                self._append_node_detail_field(lines, "系列数量", len(data_file.series))
                self._append_node_detail_field(lines, "备注", data_file.notes)
        elif kind == "source_file" and node is not None:
            source_file = project_manager.get_source_file(node.source_file_id)
            if source_file is not None:
                self._append_node_detail_section(lines, "源文件")
                self._append_node_detail_field(lines, "源文件 ID", source_file.id)
                self._append_node_detail_field(lines, "当前路径", project_manager.resolve_source_file_path(source_file, project))
                self._append_node_detail_field(lines, "原始路径", project_manager.resolve_source_file_origin_path(source_file, project))
                self._append_node_detail_field(lines, "导入时间", source_file.import_time)
                if source_file.file_size:
                    self._append_node_detail_field(lines, "文件大小", self._format_file_size(source_file.file_size))
                self._append_node_detail_field(lines, "备注", source_file.notes)
        elif kind == "series":
            series = project.find_series(node_id)
            if series is not None:
                owner_kind, owner = self._find_series_owner(project, node_id)
                self._append_node_detail_section(lines, "数据系列")
                self._append_node_detail_field(lines, "系列 ID", series.id)
                self._append_node_detail_field(lines, "所属容器", getattr(owner, "name", None))
                self._append_node_detail_field(lines, "所属容器类型", "数据文件" if owner_kind == "data_file" else "数据集" if owner_kind == "dataset" else None)
                self._append_node_detail_field(lines, "X 标签", series.x_label)
                self._append_node_detail_field(lines, "Y 标签", series.y_label)
                self._append_node_detail_field(lines, "X 点数", len(series.x))
                self._append_node_detail_field(lines, "Y 点数", len(series.y))
                self._append_node_detail_field(lines, "误差棒点数", len(series.y_err or []))
                self._append_node_detail_field(lines, "可见", series.visible)
                self._append_node_detail_field(lines, "来源", series.source)
                self._append_node_detail_field(lines, "来源曲线 ID", series.source_curve_id)
        elif kind == "curve":
            curve = self._find_curve(project, node_id)
            if curve is not None:
                owner_image = self._find_curve_owner_image(project, node_id)
                calibration = getattr(curve, "calibration", None)
                self._append_node_detail_section(lines, "图像曲线")
                self._append_node_detail_field(lines, "曲线 ID", curve.id)
                self._append_node_detail_field(lines, "所属图像", getattr(owner_image, "name", None))
                self._append_node_detail_field(lines, "像素点数量", len(curve.x_data))
                self._append_node_detail_field(lines, "真实点数量", len(curve.x_actual))
                self._append_node_detail_field(lines, "颜色", curve.color)
                self._append_node_detail_field(lines, "点形", curve.point_shape)
                self._append_node_detail_field(lines, "源图像 ID", curve.source_image_id)
                self._append_node_detail_field(lines, "校准坐标系", getattr(calibration, "coord_type", None))
        elif kind == "image_work" and node is not None:
            image = project_manager.get_image(node.image_work_id)
            if image is not None:
                self._append_node_detail_section(lines, "图像")
                self._append_node_detail_field(lines, "图像 ID", image.id)
                self._append_node_detail_field(lines, "图像路径", image.image_path)
                self._append_node_detail_field(lines, "源图路径", image.source_image_path)
                self._append_node_detail_field(lines, "曲线数量", len(image.curves))
                self._append_node_detail_field(lines, "遮罩多边形数", len(getattr(getattr(image, "mask", None), "polygons", []) or []))
        elif kind == "picture" and node is not None:
            picture = project_manager.get_picture(node.picture_id)
            if picture is not None:
                snapshot = getattr(picture, "plot_snapshot", None)
                self._append_node_detail_section(lines, "图片")
                self._append_node_detail_field(lines, "图片 ID", picture.id)
                self._append_node_detail_field(lines, "图片路径", picture.image_path)
                self._append_node_detail_field(lines, "创建时间", picture.created_at)
                self._append_node_detail_field(lines, "快照曲线数", len(getattr(snapshot, "series", []) or []))
                self._append_node_detail_field(lines, "已应用扩展数", len(getattr(snapshot, "applied_extensions", []) or []))
        elif kind == "analysis_result" and node is not None:
            analysis = project.find_analysis(node.analysis_id)
            if analysis is not None:
                self._append_node_detail_section(lines, "分析结果")
                self._append_node_detail_field(lines, "分析 ID", analysis.id)
                self._append_node_detail_field(lines, "分析类型", analysis.analysis_type)
                self._append_node_detail_field(lines, "输入系列数", len(analysis.input_series_ids))
                self._append_node_detail_field(lines, "参数项数", len(analysis.params))
                self._append_node_detail_field(lines, "摘要项数", len(analysis.summary))
                self._append_node_detail_field(lines, "结果系列 ID", analysis.result_series_id)
                self._append_node_detail_field(lines, "创建时间", analysis.created_at)
        elif kind == "global_extension_config":
            config_item = global_assets.get_extension_config(node_id)
            if config_item is not None:
                self._append_node_detail_section(lines, "扩展配置")
                self._append_node_detail_field(lines, "配置 ID", config_item.id)
                self._append_node_detail_field(lines, "类别", self._global_extension_category_label(config_item.category))
                self._append_node_detail_field(lines, "扩展类型", config_item.extension_type)
                self._append_node_detail_field(lines, "扩展名称", config_item.extension_name)
                self._append_node_detail_field(lines, "版本", config_item.extension_version)
                self._append_node_detail_field(lines, "参数项数", len(config_item.options))
                self._append_node_detail_field(lines, "默认配置", config_item.is_default)
        elif kind == "global_pipeline":
            pipeline = global_assets.get_saved_pipeline(node_id)
            if pipeline is not None:
                self._append_node_detail_section(lines, "全局流程链")
                self._append_node_detail_field(lines, "流程链 ID", pipeline.id)
                self._append_node_detail_field(lines, "步骤数", len(pipeline.ops))
                self._append_node_detail_field(lines, "创建时间", pipeline.created_at)
                self._append_node_detail_field(lines, "描述", pipeline.description)
        elif kind == "global_report_template":
            template = global_assets.get_report_template(node_id)
            if template is not None:
                self._append_node_detail_section(lines, "全局报告模板")
                self._append_node_detail_field(lines, "模板 ID", template.id)
                self._append_node_detail_field(lines, "内置模板", template.is_builtin)
                self._append_node_detail_field(lines, "内容行数", len((template.content or "").splitlines()))
        elif kind == "global_group":
            self._append_node_detail_section(lines, "全局分组")
            self._append_node_detail_field(lines, "分组标识", node_id)
            if node_id.startswith("__global_extension_configs__:"):
                parts = node_id.split(":")
                category = parts[1] if len(parts) >= 2 else ""
                self._append_node_detail_field(lines, "类别", self._global_extension_category_label(category))
                self._append_node_detail_field(
                    lines,
                    "配置数量",
                    len(global_assets.list_extension_configs(category=category, include_defaults=True)),
                )

        return "\n".join(lines)

    def _show_current_node_details(self) -> None:
        detail_text = self._current_node_detail_text()
        if not detail_text:
            return
        title = self._current_node_name() or self._node_kind_label(self._selected_node_kind)
        dialog = _NodeDetailDialog(f"节点信息 · {title}", detail_text, parent=self._dialog_parent())
        dialog.exec()

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
        return is_protected_folder(node)

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

    def _pending_entry_label(self, file_path: str, display_name: str = "") -> str:
        path = Path(file_path)
        return display_name.strip() or self._pending_import_names.get(str(path), "").strip() or path.name

    def _pending_queue_state(self, group_type: Optional[str] = None) -> Optional[_PendingImportQueueState]:
        key = group_type or self._current_import_group()
        if key not in self._pending_import_states:
            return None
        return self._pending_import_states[key]

    def _load_pending_import_state(self, group_type: Optional[str] = None) -> None:
        state = self._pending_queue_state(group_type)
        if state is None:
            self._pending_import_paths = []
            self._pending_import_names = {}
            return
        self._pending_import_paths = list(state.paths)
        self._pending_import_names = dict(state.names)

    def _save_pending_import_state(self, group_type: Optional[str] = None) -> None:
        state = self._pending_queue_state(group_type)
        if state is None:
            return
        state.paths = list(self._pending_import_paths)
        state.names = dict(self._pending_import_names)

    def _pending_entry_tooltip(self, file_path: str) -> str:
        path = Path(file_path)
        details = [f"路径: {path}"]
        try:
            details.append(f"大小: {self._format_file_size(path.stat().st_size)}")
        except OSError:
            pass
        return "\n".join(details)

    def _refresh_source_browser(self) -> None:
        browser_dir = self._ensure_external_browser_dir()
        self._refresh_source_favorites()
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

    def _begin_rename_pending_source_item(self, item, _column: int = 0) -> None:
        if item is None or self._current_import_group() is None:
            return
        self._pending_source_list.editItem(item, 0)

    def _show_pending_source_context_menu(self, pos) -> None:
        if self._current_import_group() is None:
            return
        item = self._pending_source_list.itemAt(pos)
        if item is None:
            return
        self._pending_source_list.setCurrentItem(item)
        file_path = str(item.data(0, Qt.ItemDataRole.UserRole) or "").strip()
        menu = RoundMenu(parent=self)
        rename_action = Action(FIF.EDIT, "重命名导入名", self)
        rename_action.triggered.connect(lambda: self._begin_rename_pending_source_item(item, 0))
        menu.addAction(rename_action)
        remove_action = Action(FIF.DELETE, "移除", self)
        remove_action.triggered.connect(lambda: self._remove_pending_source_files([file_path]))
        menu.addAction(remove_action)
        menu.exec(self._pending_source_list.viewport().mapToGlobal(pos))

    def _on_pending_source_item_changed(self, item, column: int) -> None:
        if item is None or column != 0:
            return
        file_path = str(item.data(0, Qt.ItemDataRole.UserRole) or "").strip()
        if not file_path:
            return
        clean_name = item.text(0).strip() or Path(file_path).name
        self._pending_import_names[file_path] = clean_name
        if item.text(0).strip() != clean_name:
            self._pending_source_list.blockSignals(True)
            item.setText(0, clean_name)
            self._pending_source_list.blockSignals(False)
        item.setToolTip(0, self._pending_entry_tooltip(file_path))
        self._save_pending_import_state()

    def _refresh_pending_source_list(self) -> None:
        valid_paths: list[str] = []
        valid_names: dict[str, str] = {}
        self._pending_source_list.blockSignals(True)
        self._pending_source_list.clear()
        for file_path in self._pending_import_paths:
            path = Path(file_path)
            if not path.exists() or not path.is_file():
                continue
            valid_paths.append(str(path))
            display_name = self._pending_entry_label(str(path), self._pending_import_names.get(str(path), path.name))
            valid_names[str(path)] = display_name
            item = QTreeWidgetItem([display_name])
            item.setData(0, Qt.ItemDataRole.UserRole, str(path))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            item.setToolTip(0, self._pending_entry_tooltip(str(path)))
            self._pending_source_list.addTopLevelItem(item)
        self._pending_source_list.blockSignals(False)
        self._pending_import_paths = valid_paths
        self._pending_import_names = valid_names
        self._save_pending_import_state()
        self._refresh_pending_source_controls()

    def _refresh_pending_source_controls(self) -> None:
        group_type = self._current_import_group()
        has_items = bool(self._pending_import_paths)
        has_selection = bool(self._selected_pending_source_file_ids())
        is_dataset_group = group_type == "datasets"
        self._btn_remove_pending.setEnabled(has_selection)
        self._btn_clear_pending.setEnabled(has_items)
        self._btn_import_pending.setEnabled(has_items and group_type is not None)
        self._btn_import_pending_default.setVisible(is_dataset_group)
        self._btn_import_pending_default.setEnabled(has_items and is_dataset_group)

        if is_dataset_group:
            self._btn_import_pending.setText("导入到数据集")
        elif group_type == "images":
            self._btn_import_pending.setText("导入到数字化")
        elif group_type == "source_files":
            self._btn_import_pending.setText("导入为源文件")
        else:
            self._btn_import_pending.setText("执行导入")

        if has_items:
            if group_type == "source_files":
                self._pending_source_hint.setText(
                    f"当前共 {len(self._pending_import_paths)} 个外部文件待导入为源文件；可双击或右键重命名导入名。"
                )
            elif group_type == "datasets":
                self._pending_source_hint.setText(
                    f"当前共 {len(self._pending_import_paths)} 个待导入文件，将导入到数据集；可双击或右键重命名导入名。"
                )
            elif group_type == "images":
                self._pending_source_hint.setText(
                    f"当前共 {len(self._pending_import_paths)} 个待导入文件，将导入到数字化；可双击或右键重命名导入名。"
                )
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
            self._pending_import_names[normalized] = Path(normalized).name
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
        for file_path in to_remove:
            self._pending_import_names.pop(file_path, None)
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
        self._pending_import_names.clear()
        self._refresh_pending_source_list()

    def _choose_external_browser_dir(self) -> None:
        start_dir = str(self._ensure_external_browser_dir() or Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "选择系统目录", start_dir)
        if not chosen:
            return
        self._external_browser_dir = Path(chosen)
        self._remember_current_external_browser_dir()
        self._refresh_source_browser()

    def _go_to_external_browser_parent(self) -> None:
        current_dir = self._ensure_external_browser_dir()
        if current_dir is None or current_dir.parent == current_dir:
            return
        self._external_browser_dir = current_dir.parent
        self._remember_current_external_browser_dir()
        self._refresh_source_browser()

    def _on_source_browser_item_activated(self, item, _column: int) -> None:
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        entry_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if not file_path:
            return
        path = Path(str(file_path))
        if entry_type == "dir":
            self._external_browser_dir = path
            self._remember_current_external_browser_dir()
            self._refresh_source_browser()
            return
        self._append_source_files_to_pending([str(path)])

    def _show_source_file_manager(self) -> None:
        self._show_source_manager_mode()
        group_type = self._current_import_group()
        group_key = group_type or ""
        target_name = self._current_node_name() or "未命名节点"
        self._load_pending_import_state(group_type)
        self._refresh_pending_source_list()
        group_label = {
            "datasets": "数据集",
            "images": "数字化",
            "source_files": "源文件",
        }.get(group_key, "-")
        self._source_manager_target_label.setText(f"导入目标: {group_label} / {target_name}")
        if group_type == "datasets":
            self._source_browser_tabs.setCurrentIndex(0)
            self._set_preview_summary(["文件管理", "在这里浏览系统文件并导入到当前数据集文件夹。"])
        elif group_type == "images":
            self._source_browser_tabs.setCurrentIndex(0)
            self._set_preview_summary(["文件管理", "在这里浏览系统图片并导入到当前数字化文件夹。"])
        else:
            self._source_browser_tabs.setCurrentIndex(1)
            self._set_preview_summary(["文件管理", "在这里浏览系统文件并导入为当前源文件文件夹下的源文件节点。"])
        self._refresh_source_manager_tab_state()
        self._refresh_project_source_browser()
        self._refresh_source_favorites()
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
            "picture": "图片",
            "curve": "图像曲线",
            "analysis_result": "分析结果",
            "global_root": "全局资源",
            "global_group": "全局分组",
            "global_pipeline": "全局流程链",
            "global_curve_style_template": "全局曲线样式",
            "global_plot_style": "全局绘图样式",
            "global_plot_theme": "全局绘图样式",
            "global_report_template": "全局报告模板",
            "global_extension_config": "全局扩展配置",
        }
        return mapping.get(kind or "", "-")

    @staticmethod
    def _global_extension_category_label(category: str) -> str:
        mapping = {
            "plot": "绘图扩展",
            "processing": "处理扩展",
            "analysis": "分析扩展",
            "digitize": "数字化扩展",
        }
        return mapping.get(category, category or "扩展配置")

    @classmethod
    def _global_preview_node_label(cls, kind: Optional[str], node_id: Optional[str]) -> str:
        if kind == "global_root":
            return "全局资源"
        if kind == "global_group":
            mapping = {
                "__global_root__": "全局资源",
                "__global_pipelines__": "Pipelines",
                "__global_curve_styles__": "曲线样式",
                "__global_plot_styles__": "绘图样式",
                "__global_reports__": "报告模板",
                "__global_extension_configs__": "扩展配置",
            }
            if node_id in mapping:
                return mapping[node_id]
            if node_id and node_id.startswith("__global_extension_configs__:"):
                parts = node_id.split(":")
                if len(parts) >= 2:
                    return cls._global_extension_category_label(parts[1])
            return "全局分组"
        if kind == "global_pipeline" and node_id:
            item = global_assets.get_saved_pipeline(node_id)
            return item.name or node_id
        if kind == "global_curve_style_template" and node_id:
            item = global_assets.get_curve_style_template(node_id)
            return item.name or node_id
        if kind in {"global_plot_style", "global_plot_theme"} and node_id:
            style_type, asset_id = parse_plot_style_asset_key(node_id)
            if style_type == "template":
                item = global_assets.get_figure_template(asset_id)
            else:
                item = global_assets.get_plot_theme(asset_id)
            return "" if item is None else getattr(item, "name", asset_id) or asset_id
        if kind == "global_report_template" and node_id:
            item = global_assets.get_report_template(node_id)
            return item.name or node_id if item is not None else node_id
        if kind == "global_extension_config" and node_id:
            item = global_assets.get_extension_config(node_id)
            if item is None:
                return node_id
            if bool(getattr(item, "is_default", False)):
                return getattr(item, "extension_name", "") or item.name or node_id
            return item.name or getattr(item, "extension_name", "") or node_id
        return ""

    def _reset_structure_preview(self) -> None:
        self._show_preview_mode()
        self._preview_image_path = None
        self._preview_xs = []
        self._preview_ys = []
        self._preview_x_label = "X"
        self._preview_y_label = "Y"
        self._set_source_file_preview_mode_controls_visible(False)
        self._set_source_file_detail_controls_visible(False)
        self._set_source_file_sheet_controls_visible(False)
        self._set_preview_plot_type_controls_visible(False)
        self._hide_source_path_links()
        self._picture_preview_tree.clear()
        self._preview_stack.setCurrentWidget(self._picture_preview_tree)

    def _show_structure_tree_preview(self, root_item: QTreeWidgetItem, summary_lines: list[str], *, preview_name: str = "") -> None:
        self._set_extension_config_editor_mode(False)
        self._reset_structure_preview()
        self._picture_preview_tree.addTopLevelItem(root_item)
        self._picture_preview_tree.expandAll()
        self._preview_name = preview_name or root_item.text(0)
        self._set_preview_summary(summary_lines)

    @staticmethod
    def _preview_tree_icon_for_kind(kind: Optional[str]):
        mapping = {
            "folder": FIF.FOLDER,
            "source_file": FIF.DOCUMENT,
            "data_file": FIF.DOCUMENT,
            "series": getattr(FIF, "DATA_HISTOGRAM", FIF.DOCUMENT),
            "image_work": FIF.PHOTO,
            "picture": FIF.PHOTO,
            "curve": FIF.PENCIL_INK,
            "analysis_result": FIF.DOCUMENT,
            "global_root": FIF.FOLDER,
            "global_group": getattr(FIF, "FOLDER", FIF.DOCUMENT),
            "global_pipeline": FIF.DEVELOPER_TOOLS,
            "global_curve_style_template": FIF.PENCIL_INK,
            "global_plot_style": FIF.PIE_SINGLE,
            "global_plot_theme": FIF.PIE_SINGLE,
            "global_report_template": FIF.DOCUMENT,
            "global_extension_config": getattr(FIF, "SETTING", FIF.DEVELOPER_TOOLS),
        }
        return mapping.get(kind or "", getattr(FIF, "INFO", FIF.DOCUMENT))

    def _build_project_structure_preview_item(self, node) -> QTreeWidgetItem:
        node_name = getattr(node, "name", "") or "未命名节点"
        item = self._make_preview_tree_item(
            node_name,
            self._preview_tree_icon_for_kind(getattr(node, "kind", None)),
            node_name,
        )
        if getattr(node, "kind", None) == "folder":
            children = self._sorted_node_children(getattr(node, "id", ""))
            if not children:
                item.addChild(self._make_preview_tree_item("空文件夹", getattr(FIF, "INFO", FIF.DOCUMENT)))
                return item
            for child in children:
                if getattr(child, "kind", None) == "folder":
                    item.addChild(self._build_project_structure_preview_item(child))
                    continue
                child_item = self._make_preview_tree_item(
                    getattr(child, "name", "") or "未命名节点",
                    self._preview_tree_icon_for_kind(getattr(child, "kind", None)),
                    getattr(child, "name", "") or "未命名节点",
                )
                item.addChild(child_item)
            return item

        if getattr(node, "kind", None) == "picture":
            picture = project_manager.get_picture(getattr(node, "picture_id", ""))
            if picture is not None and getattr(picture, "plot_snapshot", None) is not None:
                snapshot = picture.plot_snapshot
                item.addChild(self._make_preview_tree_item(f"绘图快照: {len(snapshot.series)} 条曲线", FIF.PIE_SINGLE))
            return item

        if getattr(node, "kind", None) == "analysis_result":
            project = project_manager.current_project
            analysis = None if project is None else project.find_analysis(getattr(node, "analysis_id", ""))
            if analysis is not None:
                analysis_type = getattr(analysis, "analysis_type", "") or getattr(analysis, "summary", {}).get("analysis_type", "")
                if analysis_type:
                    item.addChild(self._make_preview_tree_item(f"类型: {analysis_type}", getattr(FIF, "INFO", FIF.DOCUMENT)))
            return item

        if getattr(node, "kind", None) == "image_work":
            image = project_manager.get_image(getattr(node, "image_work_id", ""))
            if image is not None:
                item.addChild(self._make_preview_tree_item(f"曲线数量: {len(image.curves)}", getattr(FIF, "INFO", FIF.DOCUMENT)))
            return item

        if getattr(node, "kind", None) == "data_file":
            project = project_manager.current_project
            data_file = None if project is None else project.find_data_file(getattr(node, "data_file_id", ""))
            if data_file is not None:
                item.addChild(self._make_preview_tree_item(f"系列数量: {len(data_file.series)}", getattr(FIF, "INFO", FIF.DOCUMENT)))
            return item

        return item

    def _show_project_structure_preview(self, node, *, title: str, summary_lines: list[str]) -> None:
        root_item = self._build_project_structure_preview_item(node)
        self._show_structure_tree_preview(root_item, summary_lines, preview_name=title)

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

    @staticmethod
    def _extension_entry_for_category_type(category: str, extension_type: str) -> Optional[dict[str, Any]]:
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
        elif normalized_category == "digitize":
            extension = extension_registry.get_digitize(clean_type)
        else:
            extension = None
        if extension is None:
            return None
        entry = build_extension_entry(extension)
        has_config_fields = bool(entry.get("normalized_config_fields") or entry.get("config_fields"))
        return dict(entry) if entry.get("listed", True) and (entry.get("settings") or has_config_fields) else None

    def _extension_entry_for_config_item(self, config_item) -> Optional[dict[str, Any]]:
        if config_item is None:
            return None
        return self._extension_entry_for_category_type(
            str(getattr(config_item, "category", "") or ""),
            str(getattr(config_item, "extension_type", "") or ""),
        )

    def _extension_entry_for_global_group_node(self, node_id: Optional[str]) -> Optional[dict[str, Any]]:
        parts = str(node_id or "").split(":")
        if len(parts) < 3 or parts[0] != "__global_extension_configs__":
            return None
        return self._extension_entry_for_category_type(parts[1], parts[2])

    def _extension_preview_description(self, entry: Optional[dict[str, Any]], *, category: str = "") -> dict[str, str]:
        if entry is None:
            return {"title": "", "meta": ""}
        info = extension_entry_display_info(
            entry,
            category_label=self._global_extension_category_label(category) if category else "扩展",
        )
        meta_lines: list[str] = []
        if info.get("type_id"):
            meta_lines.append(f"ID: {info['type_id']}")
        if info.get("version_label"):
            meta_lines.append(f"版本: {info['version_label']}")
        if info.get("api_version_label"):
            meta_lines.append(info["api_version_label"])
        if info.get("min_app_version_label"):
            meta_lines.append(info["min_app_version_label"])
        if info.get("tested_range_label"):
            meta_lines.append(info["tested_range_label"])
        capability_parts: list[str] = []
        if info.get("capabilities_label"):
            capability_parts.append(info["capabilities_label"])
        if info.get("authority_label"):
            capability_parts.append(info["authority_label"])
        if info.get("auth_fields_label"):
            capability_parts.append(info["auth_fields_label"])
        if capability_parts:
            meta_lines.append("能力/接管: " + "；".join(capability_parts))
        if info.get("description"):
            meta_lines.append(f"描述: {info['description']}")
        return {
            "title": info.get("data_title", ""),
            "meta": "\n".join(meta_lines),
        }

    def _extension_field_help_text(self, entry: Optional[dict[str, Any]]) -> str:
        return extension_entry_parameter_help_text(entry)

    @staticmethod
    def _extension_field_error_message(field_key: str, message: str) -> str:
        return f"参数 {field_key}: {message}"

    def _validate_extension_config_payload(self, entry: Optional[dict[str, Any]], payload: dict[str, Any]) -> None:
        if entry is None:
            return
        fields = [
            dict(item)
            for item in (entry.get("normalized_config_fields") or entry.get("config_fields") or [])
            if isinstance(item, dict)
        ]
        errors: list[str] = []
        for field in fields:
            key = str(field.get("key") or "").strip()
            if not key:
                continue
            field_type = str(field.get("field_type") or "string").strip().lower()
            required = bool(field.get("required"))
            has_value = key in payload
            value = payload.get(key)
            if required and (
                not has_value
                or value is None
                or (isinstance(value, str) and not value.strip())
            ):
                errors.append(self._extension_field_error_message(key, "缺少必填值"))
                continue
            if not has_value or value is None:
                continue
            if field_type in {"string", "figure", "color"}:
                if not isinstance(value, str):
                    errors.append(self._extension_field_error_message(key, "必须是字符串"))
            elif field_type == "boolean":
                if not isinstance(value, bool):
                    errors.append(self._extension_field_error_message(key, "必须是布尔值"))
            elif field_type == "integer":
                if isinstance(value, bool) or not isinstance(value, int):
                    errors.append(self._extension_field_error_message(key, "必须是整数"))
            elif field_type in {"number", "limited"}:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    errors.append(self._extension_field_error_message(key, "必须是数值"))
                else:
                    min_value = field.get("min_value")
                    max_value = field.get("max_value")
                    if min_value is not None and float(value) < float(min_value):
                        errors.append(self._extension_field_error_message(key, f"不能小于 {min_value}"))
                    if max_value is not None and float(value) > float(max_value):
                        errors.append(self._extension_field_error_message(key, f"不能大于 {max_value}"))
            elif field_type == "selective":
                if not isinstance(value, str):
                    errors.append(self._extension_field_error_message(key, "必须是字符串选项"))
                else:
                    choices = [str(item) for item in (field.get("choices") or []) if str(item)]
                    if choices and value not in choices:
                        errors.append(self._extension_field_error_message(key, f"必须是以下值之一: {', '.join(choices)}"))
            elif field_type == "lines":
                extra = dict(field.get("extra") or {}) if isinstance(field.get("extra"), dict) else {}
                lines_number = normalize_extension_lines_number(extra.get("lines_number"))
                try:
                    validate_extension_lines_list(value, lines_number, present=True)
                except ValueError as exc:
                    errors.append(self._extension_field_error_message("lines", str(exc)))
        if errors:
            raise ValueError("；".join(errors))

    def _show_extension_config_editor(self, config_id: str) -> bool:
        config_item = global_assets.get_extension_config(config_id)
        if config_item is None:
            return False
        entry = self._extension_entry_for_config_item(config_item)
        self._show_preview_mode()
        self._current_extension_config_id = config_id
        self._set_extension_config_editor_mode(True)
        self._preview_image_path = None
        self._set_source_file_preview_mode_controls_visible(False)
        self._set_source_file_detail_controls_visible(False)
        self._set_preview_plot_type_controls_visible(False)
        self._hide_source_path_links()
        self._preview_xs = []
        self._preview_ys = []
        self._preview_name = str(getattr(config_item, "name", "") or "扩展配置")
        self._preview_x_label = "X"
        self._preview_y_label = "Y"
        self._extension_config_original_text = json.dumps(
            dict(getattr(config_item, "options", {}) or {}),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        self._text_preview.setPlainText(self._extension_config_original_text)
        self._preview_stack.setCurrentWidget(self._text_preview)
        summary_lines = [
            f"配置名称: {getattr(config_item, 'name', '') or '未命名配置'}",
            f"扩展: {getattr(config_item, 'extension_name', '') or getattr(config_item, 'extension_type', '') or '未知扩展'}",
            f"类别: {self._node_kind_label('global_group')} / {str(getattr(config_item, 'category', '') or '').strip() or 'unknown'}",
            f"类型 ID: {getattr(config_item, 'extension_type', '') or 'unknown'}",
            f"参数项: {len(dict(getattr(config_item, 'options', {}) or {}))}",
        ]
        if entry is not None:
            required_keys = [
                str(field.get("key") or "").strip()
                for field in (entry.get("normalized_config_fields") or [])
                if isinstance(field, dict) and field.get("required") and str(field.get("key") or "").strip()
            ]
            if required_keys:
                summary_lines.append(f"必填参数: {', '.join(required_keys)}")
        else:
            summary_lines.append("当前扩展未注册，无法执行字段级校验")
        self._config_editor_title_label.setText(summary_lines[0])
        self._config_editor_meta_label.setText("\n".join(summary_lines[1:]))
        self._set_preview_summary(summary_lines)
        self._set_extension_field_help_height(_EXTENSION_FIELD_HELP_COMPACT_HEIGHT)
        self._set_extension_preview_help(
            self._extension_preview_description(entry, category=str(getattr(config_item, "category", "") or "")),
            self._extension_field_help_text(entry),
        )
        self._extension_preview_panel.setVisible(True)
        return True

    def _show_global_template_editor(self, kind: str, node_id: str) -> bool:
        title, summary_lines, raw_text = self._global_template_editor_payload(kind, node_id)
        if raw_text is None:
            return False
        self._preview_editor_kind = kind
        self._preview_editor_node_id = node_id
        self._preview_editor_original_text = raw_text
        self._show_preview_mode()
        self._set_preview_text_editor_mode(
            True,
            section_label="模板编辑",
            reset_text="重置模板",
            save_text="保存模板",
            summary_title=title,
            summary_meta="\n".join(summary_lines[1:]),
        )
        self._preview_image_path = None
        self._set_source_file_preview_mode_controls_visible(False)
        self._set_source_file_detail_controls_visible(False)
        self._set_preview_plot_type_controls_visible(False)
        self._hide_source_path_links()
        self._preview_xs = []
        self._preview_ys = []
        self._preview_name = title
        self._preview_x_label = "X"
        self._preview_y_label = "Y"
        self._text_preview.setPlainText(raw_text)
        self._preview_stack.setCurrentWidget(self._text_preview)
        self._set_preview_summary(summary_lines)
        self._set_extension_field_help_height(_EXTENSION_FIELD_HELP_COMPACT_HEIGHT)
        self._set_extension_preview_help()
        self._extension_preview_panel.setVisible(False)
        return True

    def _global_template_editor_payload(self, kind: str, node_id: str) -> tuple[str, list[str], Optional[str]]:
        if kind == "global_pipeline":
            template = global_assets.get_saved_pipeline(node_id)
            if template is None:
                return "", [], None
            title = template.name or "Pipelines 模板"
            return (
                title,
                [
                    f"模板名称: {template.name or '未命名流程'}",
                    "类型: Pipelines 模板",
                    f"步骤数: {len(getattr(template, 'ops', []) or [])}",
                    f"说明: {getattr(template, 'description', '') or '无'}",
                ],
                json.dumps(template.model_dump(), ensure_ascii=False, indent=2),
            )
        if kind == "global_curve_style_template":
            template = global_assets.get_curve_style_template(node_id)
            if template is None:
                return "", [], None
            title = template.name or "曲线样式模板"
            return (
                title,
                [
                    f"模板名称: {template.name or '默认模板'}",
                    "类型: 曲线样式模板",
                    f"内置: {'是' if bool(getattr(template, 'is_builtin', False)) else '否'}",
                ],
                json.dumps(template.model_dump(), ensure_ascii=False, indent=2),
            )
        if kind in {"global_plot_style", "global_plot_theme"}:
            style_type, asset_id = parse_plot_style_asset_key(node_id)
            if style_type == "template":
                template = global_assets.get_figure_template(asset_id)
                if template is None:
                    return "", [], None
                title = template.name or "图表模板"
                return (
                    title,
                    [
                        f"模板名称: {template.name or '默认模板'}",
                        "类型: 图表模板",
                        f"主题: {template.theme or 'default'}",
                        f"图例项: {len(getattr(template, 'typed_series_refs', []) or [])}",
                    ],
                    json.dumps(template.model_dump(), ensure_ascii=False, indent=2),
                )
            theme = global_assets.get_plot_theme(asset_id)
            if theme is None:
                return "", [], None
            title = theme.name or "绘图样式"
            return (
                title,
                [
                    f"模板名称: {theme.name or '默认模板'}",
                    "类型: 绘图样式",
                    f"说明: {getattr(theme, 'description', '') or '无'}",
                    f"内置: {'是' if bool(getattr(theme, 'is_builtin', False)) else '否'}",
                ],
                json.dumps(theme.model_dump(), ensure_ascii=False, indent=2),
            )
        if kind == "global_report_template":
            template = global_assets.get_report_template(node_id)
            if template is None:
                return "", [], None
            title = template.name or "报告模板"
            return (
                title,
                [
                    f"模板名称: {template.name or '未命名模板'}",
                    "类型: 报告模板",
                    f"内置: {'是' if bool(getattr(template, 'is_builtin', False)) else '否'}",
                ],
                template.content or "",
            )
        return "", [], None

    def _reset_selected_preview_editor(self) -> None:
        if self._current_extension_config_id:
            self._text_preview.setPlainText(self._extension_config_original_text or "{}")
            return
        if self._preview_editor_kind is not None:
            self._text_preview.setPlainText(self._preview_editor_original_text or "")

    def _save_selected_preview_editor(self) -> None:
        if self._current_extension_config_id:
            self._save_selected_extension_config()
            return
        kind = self._preview_editor_kind
        node_id = self._preview_editor_node_id
        if not kind or not node_id:
            return
        raw_text = self._text_preview.toPlainText()
        if kind == "global_pipeline":
            self._save_global_pipeline_template(node_id, raw_text)
            return
        if kind == "global_curve_style_template":
            self._save_global_curve_style_template(node_id, raw_text)
            return
        if kind in {"global_plot_style", "global_plot_theme"}:
            self._save_global_plot_template(kind, node_id, raw_text)
            return
        if kind == "global_report_template":
            self._save_global_report_template(node_id, raw_text)
            return
        InfoBar.warning("保存失败", "当前模板不支持编辑保存", parent=self, position=InfoBarPosition.TOP)

    def _save_global_pipeline_template(self, template_id: str, raw_text: str) -> None:
        item = global_assets.get_saved_pipeline(template_id)
        if item is None:
            InfoBar.warning("保存失败", "当前 Pipeline 模板不存在", parent=self, position=InfoBarPosition.TOP)
            return
        try:
            payload = json.loads(raw_text)
            model = SavedPipeline.model_validate(payload)
        except json.JSONDecodeError as exc:
            InfoBar.warning("保存失败", f"JSON 格式错误：第 {exc.lineno} 行，第 {exc.colno} 列附近", parent=self, position=InfoBarPosition.TOP)
            return
        except Exception as exc:
            InfoBar.warning("保存失败", str(exc), parent=self, position=InfoBarPosition.TOP)
            return
        if not global_assets.update_saved_pipeline(template_id, name=model.name, ops=list(model.ops), description=model.description):
            InfoBar.warning("保存失败", "当前 Pipeline 模板未能更新", parent=self, position=InfoBarPosition.TOP)
            return
        self.project_modified.emit()
        self._show_global_template_editor("global_pipeline", template_id)
        self._refresh_management_panel()
        InfoBar.success("已保存", f'Pipeline 模板 "{model.name or item.name}" 已更新', parent=self, position=InfoBarPosition.TOP)

    def _save_global_curve_style_template(self, template_id: str, raw_text: str) -> None:
        template = global_assets.get_curve_style_template(template_id)
        if template is None:
            InfoBar.warning("保存失败", "当前曲线样式不存在", parent=self, position=InfoBarPosition.TOP)
            return
        try:
            payload = json.loads(raw_text)
            model = CurveStyleTemplate.model_validate(payload)
        except json.JSONDecodeError as exc:
            InfoBar.warning("保存失败", f"JSON 格式错误：第 {exc.lineno} 行，第 {exc.colno} 列附近", parent=self, position=InfoBarPosition.TOP)
            return
        except Exception as exc:
            InfoBar.warning("保存失败", str(exc), parent=self, position=InfoBarPosition.TOP)
            return
        if not global_assets.update_curve_style_template(template_id, name=model.name, description=model.description, style=model.style):
            InfoBar.warning("保存失败", "当前曲线样式未能更新", parent=self, position=InfoBarPosition.TOP)
            return
        self.project_modified.emit()
        self._show_global_template_editor("global_curve_style_template", template_id)
        self._refresh_management_panel()
        InfoBar.success("已保存", f'曲线样式 "{model.name or template.name}" 已更新', parent=self, position=InfoBarPosition.TOP)

    def _save_global_plot_template(self, kind: str, node_id: str, raw_text: str) -> None:
        style_type, asset_id = parse_plot_style_asset_key(node_id)
        if style_type != "template":
            theme = global_assets.get_plot_theme(asset_id)
            if theme is None:
                InfoBar.warning("保存失败", "当前绘图主题不存在", parent=self, position=InfoBarPosition.TOP)
                return
            try:
                payload = json.loads(raw_text)
                model = PlotTheme.model_validate(payload)
            except json.JSONDecodeError as exc:
                InfoBar.warning("保存失败", f"JSON 格式错误：第 {exc.lineno} 行，第 {exc.colno} 列附近", parent=self, position=InfoBarPosition.TOP)
                return
            except Exception as exc:
                InfoBar.warning("保存失败", str(exc), parent=self, position=InfoBarPosition.TOP)
                return
            if not global_assets.update_plot_theme(
                asset_id,
                name=model.name,
                description=model.description,
                canvas_mode=model.canvas_mode,
                grid_color=model.grid_color,
                foreground_color=model.foreground_color,
                background_color=model.background_color,
                state=model.state,
            ):
                InfoBar.warning("保存失败", "当前绘图主题未能更新", parent=self, position=InfoBarPosition.TOP)
                return
            self.project_modified.emit()
            self._show_global_template_editor(kind, node_id)
            self._refresh_management_panel()
            InfoBar.success("已保存", f'绘图主题 "{model.name or theme.name}" 已更新', parent=self, position=InfoBarPosition.TOP)
            return

        template = global_assets.get_figure_template(asset_id)
        if template is None:
            InfoBar.warning("保存失败", "当前图表模板不存在", parent=self, position=InfoBarPosition.TOP)
            return
        try:
            payload = json.loads(raw_text)
            model = FigureConfig.model_validate(payload)
        except json.JSONDecodeError as exc:
            InfoBar.warning("保存失败", f"JSON 格式错误：第 {exc.lineno} 行，第 {exc.colno} 列附近", parent=self, position=InfoBarPosition.TOP)
            return
        except Exception as exc:
            InfoBar.warning("保存失败", str(exc), parent=self, position=InfoBarPosition.TOP)
            return
        if not global_assets.update_figure_template(asset_id, template=model):
            InfoBar.warning("保存失败", "当前图表模板未能更新", parent=self, position=InfoBarPosition.TOP)
            return
        self.project_modified.emit()
        self._show_global_template_editor(kind, node_id)
        self._refresh_management_panel()
        InfoBar.success("已保存", f'图表模板 "{model.name or template.name}" 已更新', parent=self, position=InfoBarPosition.TOP)

    def _save_global_report_template(self, template_id: str, raw_text: str) -> None:
        template = global_assets.get_report_template(template_id)
        if template is None:
            InfoBar.warning("保存失败", "当前报告模板不存在", parent=self, position=InfoBarPosition.TOP)
            return
        if global_assets.update_report_template(template_id, content=raw_text):
            self.project_modified.emit()
            self._show_global_template_editor("global_report_template", template_id)
            self._refresh_management_panel()
            InfoBar.success("已保存", f'报告模板 "{template.name}" 已更新', parent=self, position=InfoBarPosition.TOP)
            return
        fallback_name, ok = TextInputDialog.get_text(
            self,
            "另存报告模板",
            "模板名称:",
            placeholder="输入新模板名称",
            text=f"{template.name} 副本",
        )
        if not ok or not fallback_name.strip():
            return
        copied = global_assets.add_report_template(ReportTemplate(name=fallback_name.strip(), content=raw_text))
        self.project_modified.emit()
        self._show_global_template_editor("global_report_template", copied.id)
        self._refresh_management_panel()
        InfoBar.success("已保存", f'报告模板 "{copied.name}" 已另存', parent=self, position=InfoBarPosition.TOP)

    def _reset_selected_extension_config_edit(self) -> None:
        if not self._current_extension_config_id:
            self._reset_selected_preview_editor()
            return
        self._text_preview.setPlainText(self._extension_config_original_text or "{}")

    def _save_selected_extension_config(self) -> None:
        config_id = self._current_extension_config_id or self._selected_node_id
        if self._current_extension_config_id is None and self._preview_editor_kind is not None:
            self._save_selected_preview_editor()
            return
        if not config_id:
            return
        config_item = global_assets.get_extension_config(config_id)
        if config_item is None:
            InfoBar.warning("保存失败", "当前扩展配置不存在", parent=self, position=InfoBarPosition.TOP)
            return
        if bool(getattr(config_item, "is_default", False)):
            InfoBar.warning("保存失败", "默认配置不支持直接修改，请先创建副本", parent=self, position=InfoBarPosition.TOP)
            return
        raw_text = self._text_preview.toPlainText().strip() or "{}"
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            InfoBar.warning(
                "保存失败",
                f"JSON 格式错误：第 {exc.lineno} 行，第 {exc.colno} 列附近",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return
        if not isinstance(payload, dict):
            InfoBar.warning("保存失败", "配置内容必须是 JSON 对象", parent=self, position=InfoBarPosition.TOP)
            return
        entry = self._extension_entry_for_config_item(config_item)
        try:
            self._validate_extension_config_payload(entry, payload)
            updated = global_assets.update_extension_config(
                config_id,
                options=payload,
                extension_version=(str(entry.get("version") or "") if entry is not None else getattr(config_item, "extension_version", None)),
            )
        except ValueError as exc:
            InfoBar.warning("保存失败", str(exc), parent=self, position=InfoBarPosition.TOP)
            return
        if updated is None:
            InfoBar.warning("保存失败", "扩展配置未能更新", parent=self, position=InfoBarPosition.TOP)
            return
        self.project_modified.emit()
        self._show_extension_config_editor(config_id)
        self._refresh_management_panel()
        InfoBar.success("已保存", f'配置 "{updated.name}" 已更新', parent=self, position=InfoBarPosition.TOP)

    def _build_global_extension_items(self, category: str) -> list[QTreeWidgetItem]:
        items: list[QTreeWidgetItem] = []
        name_map = self._extension_registry_name_map(category)
        grouped: dict[str, list[object]] = {type_id: [] for type_id in name_map}
        for config in global_assets.list_extension_configs(category=category, include_defaults=False):
            type_id = str(getattr(config, "extension_type", "") or "").strip()
            if not type_id or type_id not in name_map:
                continue
            grouped.setdefault(type_id, []).append(config)

        for type_id in sorted(name_map, key=lambda value: (name_map.get(value, value).lower(), value)):
            configs = sorted(grouped.get(type_id, []), key=lambda item: (str(getattr(item, "name", "") or "").lower(), str(getattr(item, "id", "") or "")))
            extension_label = name_map.get(type_id, type_id)
            group_item = self._make_preview_tree_item(extension_label, getattr(FIF, "SETTING", FIF.DEVELOPER_TOOLS), extension_label)
            for config in configs:
                group_item.addChild(self._build_global_preview_item("global_extension_config", getattr(config, "id", "")))
            items.append(group_item)
        return items

    def _build_global_preview_item(self, kind: str, node_id: str) -> QTreeWidgetItem:
        label = self._global_preview_node_label(kind, node_id) or "未命名节点"
        item = self._make_preview_tree_item(label, self._preview_tree_icon_for_kind(kind), label)

        if kind == "global_root":
            for child_kind, child_id in (
                ("global_group", "__global_pipelines__"),
                ("global_group", "__global_curve_styles__"),
                ("global_group", "__global_plot_styles__"),
                ("global_group", "__global_reports__"),
                ("global_group", "__global_extension_configs__"),
            ):
                item.addChild(self._build_global_preview_item(child_kind, child_id))
            return item

        if kind == "global_group":
            if node_id == "__global_pipelines__":
                children = [self._build_global_preview_item("global_pipeline", pipeline.id) for pipeline in global_assets.list_saved_pipelines()]
            elif node_id == "__global_curve_styles__":
                children = [self._build_global_preview_item("global_curve_style_template", style.id) for style in global_assets.list_curve_style_templates()]
            elif node_id == "__global_plot_styles__":
                children = [
                    self._build_global_preview_item("global_plot_style", f"theme:{style.id or style.name}")
                    for style in global_assets.list_plot_themes(include_builtin=True)
                ]
                children.extend(
                    self._build_global_preview_item("global_plot_style", f"template:{style.id}")
                    for style in global_assets.list_figure_templates()
                )
            elif node_id == "__global_reports__":
                children = [self._build_global_preview_item("global_report_template", template.id) for template in global_assets.list_report_templates(include_builtin=True)]
            elif node_id == "__global_extension_configs__":
                children = [
                    self._build_global_preview_item("global_group", f"__global_extension_configs__:{category}")
                    for category in ("plot", "processing", "analysis", "digitize")
                ]
            elif node_id.startswith("__global_extension_configs__:"):
                parts = node_id.split(":")
                category = parts[1] if len(parts) >= 2 else ""
                if len(parts) >= 3:
                    entry = self._extension_entry_for_category_type(category, parts[2])
                    if entry is not None:
                        description = str(entry.get("description") or "").strip()
                        if description:
                            item.addChild(self._make_preview_tree_item(f"说明: {description}", getattr(FIF, "INFO", FIF.DOCUMENT)))
                        field_count = len([
                            field
                            for field in (entry.get("normalized_config_fields") or entry.get("config_fields") or [])
                            if isinstance(field, dict)
                        ])
                        item.addChild(self._make_preview_tree_item(f"参数字段: {field_count}", getattr(FIF, "INFO", FIF.DOCUMENT)))
                    configs = [
                        config
                        for config in global_assets.list_extension_configs(category=category, extension_type=parts[2])
                        if str(getattr(config, "extension_type", "") or "").strip() == parts[2]
                    ]
                    children = [self._build_global_preview_item("global_extension_config", getattr(config, "id", "")) for config in configs]
                else:
                    children = self._build_global_extension_items(category)
            else:
                children = []
            if not children:
                item.addChild(self._make_preview_tree_item("空分组", getattr(FIF, "INFO", FIF.DOCUMENT)))
                return item
            for child in children:
                item.addChild(child)
            return item

        if kind == "global_pipeline":
            pipeline = global_assets.get_saved_pipeline(node_id)
            if pipeline is not None:
                item.addChild(self._make_preview_tree_item(f"步骤数: {len(getattr(pipeline, 'ops', []) or [])}", getattr(FIF, "INFO", FIF.DOCUMENT)))
                if getattr(pipeline, "description", ""):
                    item.addChild(self._make_preview_tree_item(f"说明: {pipeline.description}", getattr(FIF, "INFO", FIF.DOCUMENT)))
            return item

        if kind == "global_curve_style_template":
            template = global_assets.get_curve_style_template(node_id)
            if template is not None:
                if getattr(template, "description", ""):
                    item.addChild(self._make_preview_tree_item(f"说明: {template.description}", getattr(FIF, "INFO", FIF.DOCUMENT)))
                if getattr(template, "created_at", ""):
                    item.addChild(self._make_preview_tree_item(f"创建时间: {template.created_at}", getattr(FIF, "DATE_TIME", FIF.DOCUMENT)))
            return item

        if kind in {"global_plot_style", "global_plot_theme"}:
            style_type, asset_id = parse_plot_style_asset_key(node_id)
            if style_type == "template":
                template = global_assets.get_figure_template(asset_id)
                if template is not None:
                    item.addChild(self._make_preview_tree_item("类型: 图形模板", getattr(FIF, "INFO", FIF.DOCUMENT)))
                    if getattr(template, "theme", ""):
                        item.addChild(self._make_preview_tree_item(f"主题: {template.theme}", FIF.PIE_SINGLE))
                    typed_axis = getattr(template, "typed_axis_config", None)
                    if typed_axis is not None:
                        if getattr(typed_axis, "x_label", ""):
                            item.addChild(self._make_preview_tree_item(f"X 轴: {typed_axis.x_label}", getattr(FIF, "INFO", FIF.DOCUMENT)))
                        if getattr(typed_axis, "y_label", ""):
                            item.addChild(self._make_preview_tree_item(f"Y 轴: {typed_axis.y_label}", getattr(FIF, "INFO", FIF.DOCUMENT)))
            else:
                theme = global_assets.get_plot_theme(asset_id)
                if theme is not None:
                    item.addChild(self._make_preview_tree_item("类型: 主题样式", getattr(FIF, "INFO", FIF.DOCUMENT)))
                    if getattr(theme, "description", ""):
                        item.addChild(self._make_preview_tree_item(f"说明: {theme.description}", getattr(FIF, "INFO", FIF.DOCUMENT)))
                    item.addChild(self._make_preview_tree_item(f"内置: {'是' if bool(getattr(theme, 'is_builtin', False)) else '否'}", getattr(FIF, "INFO", FIF.DOCUMENT)))
            return item

        if kind == "global_report_template":
            template = global_assets.get_report_template(node_id)
            if template is not None:
                item.addChild(self._make_preview_tree_item(f"内置: {'是' if bool(getattr(template, 'is_builtin', False)) else '否'}", getattr(FIF, "INFO", FIF.DOCUMENT)))
                line_count = len((getattr(template, "content", "") or "").splitlines())
                item.addChild(self._make_preview_tree_item(f"内容行数: {line_count}", getattr(FIF, "INFO", FIF.DOCUMENT)))
            return item

        if kind == "global_extension_config":
            config = global_assets.get_extension_config(node_id)
            if config is not None:
                item.addChild(self._make_preview_tree_item(f"扩展: {getattr(config, 'extension_name', '') or getattr(config, 'extension_type', '-')}", getattr(FIF, "INFO", FIF.DOCUMENT)))
                item.addChild(self._make_preview_tree_item(f"分类: {self._global_extension_category_label(getattr(config, 'category', ''))}", getattr(FIF, "INFO", FIF.DOCUMENT)))
                item.addChild(self._make_preview_tree_item(f"默认配置: {'是' if bool(getattr(config, 'is_default', False)) else '否'}", getattr(FIF, "INFO", FIF.DOCUMENT)))
                item.addChild(self._make_preview_tree_item(f"参数项: {len(getattr(config, 'options', {}) or {})}", getattr(FIF, "INFO", FIF.DOCUMENT)))
                entry = self._extension_entry_for_config_item(config)
                if entry is not None:
                    description = str(entry.get("description") or "").strip()
                    if description:
                        item.addChild(self._make_preview_tree_item(f"说明: {description}", getattr(FIF, "INFO", FIF.DOCUMENT)))
            return item

        return item

    def _show_global_resource_preview(self, kind: str, node_id: str) -> bool:
        if not kind.startswith("global_"):
            return False
        root_item = self._build_global_preview_item(kind, node_id)
        summary_lines = [f"{self._node_kind_label(kind)}: {root_item.text(0)}"]
        extension_entry = None
        extension_category = ""
        if kind == "global_root":
            summary_lines.extend([
                f"Pipelines: {len(global_assets.list_saved_pipelines())}",
                f"曲线样式: {len(global_assets.list_curve_style_templates())}",
                f"绘图样式: {len(global_assets.list_plot_themes(include_builtin=True)) + len(global_assets.list_figure_templates())}",
                f"报告模板: {len(global_assets.list_report_templates(include_builtin=True))}",
                f"扩展配置: {len(global_assets.list_extension_configs())}",
            ])
        elif kind == "global_group":
            parts = str(node_id or "").split(":")
            if len(parts) >= 3 and parts[0] == "__global_extension_configs__":
                extension_category = parts[1]
                extension_entry = self._extension_entry_for_global_group_node(node_id)
                description = "" if extension_entry is None else str(extension_entry.get("description") or "").strip()
                summary_lines.append(description or f"配置数量: {max(root_item.childCount() - 1, 0)}")
            else:
                summary_lines.append(f"子节点数量: {root_item.childCount()}")
        elif kind == "global_pipeline":
            pipeline = global_assets.get_saved_pipeline(node_id)
            if pipeline is not None:
                summary_lines.append(f"步骤数: {len(getattr(pipeline, 'ops', []) or [])}")
        elif kind == "global_report_template":
            template = global_assets.get_report_template(node_id)
            if template is not None:
                summary_lines.append(f"内置: {'是' if bool(getattr(template, 'is_builtin', False)) else '否'}")
        elif kind == "global_extension_config":
            config = global_assets.get_extension_config(node_id)
            if config is not None:
                extension_category = str(getattr(config, "category", "") or "")
                extension_entry = self._extension_entry_for_config_item(config)
                summary_lines.append(f"参数项: {len(getattr(config, 'options', {}) or {})}")
        self._show_structure_tree_preview(root_item, summary_lines, preview_name=root_item.text(0))
        self._set_extension_field_help_height(
            _EXTENSION_FIELD_HELP_EXPANDED_HEIGHT
            if extension_entry is not None and kind != "global_extension_config"
            else _EXTENSION_FIELD_HELP_COMPACT_HEIGHT
        )
        self._set_extension_preview_help(
            self._extension_preview_description(extension_entry, category=extension_category),
            self._extension_field_help_text(extension_entry),
        )
        self._set_preview_footer_visible(extension_entry is None)
        return True

    def _can_rename_current_node(self) -> bool:
        if not self._selected_node_kind or not self._selected_node_id:
            return False
        if self._selected_node_kind == "global_extension_config":
            config_item = global_assets.get_extension_config(self._selected_node_id)
            return bool(config_item is not None and not bool(getattr(config_item, "is_default", False)))
        if self._selected_node_kind in {"source_file", "data_file", "series", "curve", "image_work", "picture"}:
            return True
        if self._selected_node_kind == "folder":
            return not self._is_protected_folder_node(self._current_tree_node())
        return False

    def _can_delete_current_node(self) -> bool:
        if not self._selected_node_kind or not self._selected_node_id:
            return False
        if self._selected_node_kind == "global_extension_config":
            config_item = global_assets.get_extension_config(self._selected_node_id)
            return bool(config_item is not None and not bool(getattr(config_item, "is_default", False)))
        if self._selected_node_kind in {"source_file", "data_file", "series", "curve", "image_work", "picture"}:
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
            self._apply_manage_target_action_style(False)
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
        self._apply_manage_target_action_style(True)
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
        elif self._selected_node_kind == "global_extension_config":
            self._btn_export.setEnabled(False)
            self._btn_to_vis.setEnabled(False)
            self._btn_to_proc.setEnabled(False)
            self._manage_help_label.setText("该扩展配置已切换到右侧 JSON 编辑器；保存前会检查 JSON 格式和必填参数。")
        elif is_source_file_leaf:
            source_path = self._current_source_file_path()
            self._btn_import_source_to_data.setEnabled(bool(source_path) and self._supports_dataset_import(source_path))
            self._btn_import_source_to_digitize.setEnabled(bool(source_path) and self._supports_digitize_import(source_path))
            self._manage_help_label.setText("源文件节点支持重命名、删除，以及按文件类型直接导入到数据集或数字化。")
        elif import_group == "source_files":
            self._manage_help_label.setText("源文件文件夹可重命名/删除；右侧文件管理器用于浏览系统文件并导入为源文件。")
        elif import_group == "datasets":
            self._manage_help_label.setText("数据集文件夹可重命名/删除；右侧文件管理器用于浏览外部数据文件并导入到当前数据集目录。")
        elif import_group == "images":
            self._manage_help_label.setText("数字化文件夹可重命名/删除；右侧文件管理器用于浏览系统图片并导入到当前数字化目录。")
        else:
            self._manage_help_label.setText("数据文件、系列、图像、图片和分析结果按当前节点能力开放重命名、删除、导出或继续流转。")
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

    def _preview_navigation_mode(self) -> str:
        return preview_navigation_mode(getattr(self, "_preview_nav_toolbar", None))

    def _sync_preview_nav_toggle_states(self) -> None:
        sync_preview_nav_toggle_states(
            getattr(self, "_preview_nav_toolbar", None),
            getattr(self, "_preview_pan_btn", None),
            getattr(self, "_preview_box_zoom_btn", None),
        )

    def _toggle_preview_pan_mode(self, checked: bool) -> None:
        toggle_preview_pan_mode(
            getattr(self, "_preview_nav_toolbar", None),
            getattr(self, "_preview_pan_btn", None),
            getattr(self, "_preview_box_zoom_btn", None),
            checked,
        )

    def _toggle_preview_box_zoom_mode(self, checked: bool) -> None:
        toggle_preview_box_zoom_mode(
            getattr(self, "_preview_nav_toolbar", None),
            getattr(self, "_preview_pan_btn", None),
            getattr(self, "_preview_box_zoom_btn", None),
            checked,
        )

    def _zoom_preview_axes(self, factor: float) -> None:
        zoom_figure_axes(self._preview_figure, self._preview_canvas, factor, redraw_callback=self._draw_preview)

    def _reset_preview_view(self) -> None:
        self._draw_preview()
        self._sync_preview_nav_toggle_states()

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
        self._sync_preview_nav_toggle_states()

    def _show_xy_preview(self, xs, ys, name: str, x_label: str = "X", y_label: str = "Y"):
        """填充绘图预览和统计摘要。"""
        self._set_extension_config_editor_mode(False)
        self._show_preview_mode()
        self._preview_image_path = None
        self._set_source_file_preview_mode_controls_visible(False)
        self._set_source_file_detail_controls_visible(False)
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
            self._set_preview_summary([
                name or "数据预览",
                f"N = {n}",
                f"X: [{x_min:.4g}, {x_max:.4g}]",
                f"Y: [{y_min:.4g}, {y_max:.4g}]",
                f"均值 = {y_mean:.4g}",
                f"标准差 = {y_std:.4g}",
            ])

    def _show_text_preview(self, title: str, content: str, stats_text: str | list[str], *, show_source_file_controls: bool = False) -> None:
        self._set_extension_config_editor_mode(False)
        self._show_preview_mode()
        self._preview_image_path = None
        self._set_source_file_preview_mode_controls_visible(show_source_file_controls)
        self._set_source_file_detail_controls_visible(False)
        self._set_preview_plot_type_controls_visible(False)
        self._hide_source_path_links()
        self._preview_xs = []
        self._preview_ys = []
        self._preview_name = title
        self._preview_x_label = "X"
        self._preview_y_label = "Y"
        self._text_preview.setPlainText(content.strip())
        self._preview_stack.setCurrentWidget(self._text_preview)
        summary_lines = stats_text if isinstance(stats_text, list) else [line for line in stats_text.splitlines() if line.strip()]
        self._set_preview_summary(summary_lines or [title])

    @staticmethod
    def _format_preview_value(value) -> str:
        if value in (None, ""):
            return ""
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return str(value)
        if isinstance(value, (int, float)):
            return f"{value:.6g}"
        return str(value)

    def _build_data_file_parsed_preview(self, data_file: DataFile) -> tuple[str, str]:
        if not data_file.series:
            return (
                f"数据文件: {data_file.name}\n\n当前数据文件中暂无数据系列。",
                "当前节点为数据文件，但文件内尚无数据可预览。",
            )

        row_count = max(max(len(series.x), len(series.y)) for series in data_file.series)
        preview_rows = min(row_count, 80)
        first_series = data_file.series[0]
        header = [first_series.x_label or "X"]
        for index, series in enumerate(data_file.series, start=1):
            header.append(series.name or series.y_label or f"系列{index}")

        lines = ["\t".join(header)]
        for row_index in range(preview_rows):
            x_value = self._format_preview_value(first_series.x[row_index]) if row_index < len(first_series.x) else ""
            row = [x_value]
            for series in data_file.series:
                row.append(self._format_preview_value(series.y[row_index]) if row_index < len(series.y) else "")
            lines.append("\t".join(row))

        if preview_rows < row_count:
            lines.extend(["", f"... 已截断，显示前 {preview_rows} / {row_count} 行"])

        stats_lines = [
            f"数据文件: {data_file.name}",
            f"系列数量: {len(data_file.series)}",
            f"预览行数: {preview_rows} / {row_count}",
        ]
        if data_file.source_path.strip():
            stats_lines.append(f"源文件: {data_file.source_path}")
        return "\n".join(lines), "\n".join(stats_lines)

    def _show_parsed_source_file_preview(
        self,
        file_path: str,
        title: str,
        stats_lines: list[str],
        *,
        origin_path: str = "",
    ) -> bool:
        from ui.dialogs.import_dialog import analyze_file_preview

        state = self._preview_state_for_node(self._selected_node_id)
        try:
            result = analyze_file_preview(
                file_path,
                row_offset=state.row_offset,
                row_limit=max(1, state.row_limit),
                skip_rows=max(0, state.skip_rows),
                sheet_name=state.selected_sheet,
            )
        except Exception as exc:
            self._show_text_preview(
                title,
                f"无法解析文件预览。\n\n失败原因: {type(exc).__name__}: {exc}\n\n可以切换到“源文件”查看原始内容。",
                [
                    *stats_lines,
                    "解析状态: 失败",
                    f"失败原因: {type(exc).__name__}: {exc}",
                ],
                show_source_file_controls=True,
            )
            self._set_source_file_skip_rows_enabled(True)
            self._update_source_file_page_controls(0, 0, max(1, state.row_limit), visible=True)
            self._show_source_path_links(file_path, origin_path)
            return True

        if result.total_rows > 0 and result.row_offset >= result.total_rows:
            state.row_offset = max(result.total_rows - max(1, state.row_limit), 0)
            return self._show_parsed_source_file_preview(file_path, title, stats_lines, origin_path=origin_path)

        state.selected_sheet = result.selected_sheet
        state.last_source_path = file_path
        self._show_preview_mode()
        self._preview_image_path = None
        self._set_source_file_preview_mode_controls_visible(True)
        self._set_source_file_detail_controls_visible(True)
        self._set_source_file_skip_rows_enabled(True)
        self._set_preview_plot_type_controls_visible(False)
        self._hide_source_path_links()
        self._preview_xs = []
        self._preview_ys = []
        self._preview_name = title
        self._preview_x_label = "X"
        self._preview_y_label = "Y"

        self._configure_source_file_sheet_options(result.sheet_names, result.selected_sheet)
        self._parsed_preview_table.clear()
        self._parsed_preview_table.setRowCount(len(result.rows))
        self._parsed_preview_table.setColumnCount(len(result.headers) + 1)
        row_header_item = QTableWidgetItem("行号")
        row_header_item.setToolTip("源文件中的原始行号")
        self._parsed_preview_table.setHorizontalHeaderItem(0, row_header_item)
        for column_index, header in enumerate(result.headers, start=1):
            value_index = column_index - 1
            column_type = result.column_types[value_index] if value_index < len(result.column_types) else "-"
            header_text = str(header) if not column_type or column_type == "-" else f"{header} · {column_type}"
            header_item = QTableWidgetItem(header_text)
            header_item.setToolTip(header_text)
            self._parsed_preview_table.setHorizontalHeaderItem(column_index, header_item)

        for row_index, row in enumerate(result.rows):
            row_number_item = QTableWidgetItem(str(result.row_offset + row_index + 1))
            row_number_item.setToolTip(f"行号: {result.row_offset + row_index + 1}")
            self._parsed_preview_table.setItem(row_index, 0, row_number_item)
            for value_index, header in enumerate(result.headers):
                value = row[value_index] if value_index < len(row) else ""
                item = QTableWidgetItem(self._format_preview_value(value))
                column_type = result.column_types[value_index] if value_index < len(result.column_types) else "-"
                item.setToolTip(f"{header} ({column_type}): {item.text()}")
                self._parsed_preview_table.setItem(row_index, value_index + 1, item)

        horizontal_header = self._parsed_preview_table.horizontalHeader()
        horizontal_header.setStretchLastSection(False)
        horizontal_header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        horizontal_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for column_index in range(1, len(result.headers) + 1):
            horizontal_header.setSectionResizeMode(column_index, QHeaderView.ResizeMode.ResizeToContents)

        self._parsed_preview_table.resizeColumnsToContents()
        self._parsed_preview_table.resizeRowsToContents()
        self._preview_stack.setCurrentWidget(self._parsed_preview_table)
        self._update_source_file_page_controls(result.total_rows, result.row_offset, result.row_limit, visible=True)

        summary_lines = list(stats_lines)
        summary_lines.append(f"解析格式: {result.detected_format}")
        if result.encoding:
            summary_lines.append(f"编码: {result.encoding}")
        if result.delimiter:
            summary_lines.append(f"分隔: {result.delimiter}")
        if result.selected_sheet:
            summary_lines.append(f"工作表: {result.selected_sheet}")
        if result.applied_skip_rows > 0:
            unit = "行" if result.applied_skip_rows > 1 else "行"
            summary_lines.append(f"表头: 跳过{result.applied_skip_rows}{unit}")
        else:
            summary_lines.append("表头: 自动识别")
        summary_lines.append(f"列数: {len(result.headers)}")
        invalid_line_text = f"无效行: {result.skipped_rows}"
        if result.header_warning:
            invalid_line_text += f"（{result.header_warning}）"
        elif result.applied_skip_rows == 0 and not result.has_header:
            invalid_line_text += "（缺少表头）"
        summary_lines.append(invalid_line_text)
        self._set_preview_summary(summary_lines)
        self._show_source_path_links(file_path, origin_path)
        return True

    def _show_paginated_text_source_preview(
        self,
        file_path: str,
        title: str,
        stats_lines: list[str],
        *,
        origin_path: str = "",
        show_source_file_controls: bool = False,
    ) -> bool:
        from ui.dialogs.import_dialog import read_text_preview_page

        state = self._preview_state_for_node(self._selected_node_id)
        preview = read_text_preview_page(
            file_path,
            line_offset=state.row_offset,
            line_limit=max(1, state.row_limit),
        )
        if preview.total_lines > 0 and preview.line_offset >= preview.total_lines:
            state.row_offset = max(preview.total_lines - max(1, state.row_limit), 0)
            preview = read_text_preview_page(
                file_path,
                line_offset=state.row_offset,
                line_limit=max(1, state.row_limit),
            )

        state.last_source_path = file_path
        content = preview.content or "（当前页没有可显示内容）"
        self._show_text_preview(title, content, "\n".join(stats_lines), show_source_file_controls=show_source_file_controls)
        self._set_source_file_skip_rows_enabled(False)
        self._set_source_file_sheet_controls_visible(False)
        self._update_source_file_page_controls(
            preview.total_lines,
            preview.line_offset,
            preview.line_limit,
            visible=show_source_file_controls,
        )

        summary_lines = list(stats_lines)
        summary_lines.append(f"文本编码: {preview.encoding}")
        if preview.total_lines <= 0:
            summary_lines.append("源文件为空")
        self._set_preview_summary(summary_lines)
        self._show_source_path_links(file_path, origin_path)
        return True

    def _show_file_preview_from_path(
        self,
        file_path: str,
        title: str,
        stats_lines: list[str],
        *,
        origin_path: str = "",
        show_path_links: bool = False,
        show_source_file_controls: bool = False,
    ) -> bool:
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix in _SOURCE_IMAGE_SUFFIXES:
            self._show_preview_mode()
            self._set_source_file_preview_mode_controls_visible(show_source_file_controls)
            self._set_source_file_detail_controls_visible(False)
            self._set_source_file_sheet_controls_visible(False)
            self._set_preview_plot_type_controls_visible(False)
            self._hide_source_path_links()
            self._preview_stack.setCurrentWidget(self._image_preview_label)
            if not self._update_preview_image_from_path(str(path)):
                self._show_text_preview(title, f"无法加载图片预览。\n\n{file_path}", "\n".join(stats_lines), show_source_file_controls=show_source_file_controls)
                if show_path_links:
                    self._show_source_path_links(str(path), origin_path)
                return True
            self._set_preview_summary(stats_lines)
            if show_path_links:
                self._show_source_path_links(str(path), origin_path)
            return True

        if suffix in _TEXT_PREVIEW_SUFFIXES:
            return self._show_paginated_text_source_preview(
                str(path),
                title,
                stats_lines,
                origin_path=origin_path,
                show_source_file_controls=show_source_file_controls,
            )

        preview_lines = [f"文件名: {title}"]
        if suffix in _TABULAR_PREVIEW_SUFFIXES:
            preview_lines.append("该文件类型暂不提供内联全文预览，但支持作为数据文件导入。")
        else:
            preview_lines.append("该文件类型暂不提供内联预览，可继续使用导入或导出动作。")
        preview_lines.append("")
        preview_lines.extend(stats_lines)
        self._show_text_preview(title, "\n".join(preview_lines), "\n".join(stats_lines), show_source_file_controls=show_source_file_controls)
        self._set_source_file_sheet_controls_visible(False)
        if show_path_links:
            self._show_source_path_links(str(path), origin_path)
        return True

    def _show_image_preview(self, image_id: str, image_name: str) -> bool:
        self._set_extension_config_editor_mode(False)
        self._show_preview_mode()
        self._preview_image_path = None
        self._set_source_file_preview_mode_controls_visible(False)
        self._set_source_file_detail_controls_visible(False)
        self._set_preview_plot_type_controls_visible(False)
        self._hide_source_path_links()
        image = project_manager.get_image(image_id)
        if image is None:
            return False
        image_path = project_manager.get_image_path(image_id)
        self._preview_stack.setCurrentWidget(self._image_preview_label)
        if not self._update_preview_image_from_path(image_path):
            self._image_preview_label.setPixmap(QPixmap())
            self._image_preview_label.setText(f"无法加载图片预览\n\n{image_path or '未找到图片路径'}")
            stats_text = f"图像名称: {image_name}\n曲线数量: {len(image.curves)}"
        else:
            pixmap = QPixmap(image_path)
            stats_text = (
                f"图像名称: {image_name}\n"
                f"尺寸: {pixmap.width()} × {pixmap.height()} px\n"
                f"曲线数量: {len(image.curves)}"
            )
        self._preview_name = image_name
        self._preview_xs = []
        self._preview_ys = []
        self._set_preview_summary([line for line in stats_text.splitlines() if line.strip()])
        return True

    def _show_picture_preview(self, node_id: str) -> bool:
        self._set_extension_config_editor_mode(False)
        project = project_manager.current_project
        if project is None or project.tree is None:
            return False
        node = project.tree.get_node(node_id)
        if node is None or node.kind != "picture":
            return False
        picture_id = getattr(node, "picture_id", "")
        if not picture_id:
            return False
        picture = project_manager.get_picture(picture_id)
        if picture is None:
            return False

        picture_path = project_manager.get_picture_path(picture.id)
        pixmap = QPixmap(picture_path) if picture_path else QPixmap()
        self._reset_structure_preview()
        self._populate_picture_preview_tree(picture, picture_path, pixmap)
        if pixmap.isNull():
            stats_lines = [f"图片名称: {picture.name}", "预览状态: 加载失败"]
        else:
            stats_lines = [
                f"图片名称: {picture.name}",
                f"尺寸: {pixmap.width()} × {pixmap.height()} px",
            ]
        if picture.plot_snapshot is not None:
            stats_lines.append(f"绘图快照: {len(picture.plot_snapshot.series)} 条曲线")
        else:
            stats_lines.append("绘图快照: 未保存")

        self._preview_name = picture.name
        self._preview_xs = []
        self._preview_ys = []
        self._set_preview_summary(stats_lines)
        return True

    @staticmethod
    def _make_preview_tree_item(label: str, icon_fif=None, tooltip: Optional[str] = None) -> QTreeWidgetItem:
        item = QTreeWidgetItem([label])
        if icon_fif is not None:
            item.setIcon(0, icon_fif.icon())
        item.setToolTip(0, tooltip or label)
        return item

    def _populate_picture_preview_tree(self, picture, picture_path: str, pixmap: QPixmap) -> None:
        picture_name = picture.name or "未命名图片"
        root_item = self._make_preview_tree_item(picture_name, FIF.PHOTO, picture_path or picture_name)
        self._picture_preview_tree.addTopLevelItem(root_item)

        file_item = self._make_preview_tree_item("图片文件", FIF.PHOTO, picture_path or "未记录图片路径")
        root_item.addChild(file_item)
        display_path = picture_path or "未记录路径"
        file_item.addChild(self._make_preview_tree_item(Path(display_path).name if picture_path else display_path, FIF.DOCUMENT, display_path))
        if picture_path:
            try:
                size_text = self._format_file_size(Path(picture_path).stat().st_size)
                file_item.addChild(self._make_preview_tree_item(f"大小: {size_text}", getattr(FIF, "INFO", FIF.DOCUMENT)))
            except OSError:
                pass
        if not pixmap.isNull():
            file_item.addChild(self._make_preview_tree_item(f"尺寸: {pixmap.width()} × {pixmap.height()} px", getattr(FIF, "INFO", FIF.DOCUMENT)))
        if getattr(picture, "created_at", ""):
            file_item.addChild(self._make_preview_tree_item(f"创建时间: {picture.created_at}", getattr(FIF, "DATE_TIME", FIF.DOCUMENT)))

        snapshot_item = self._make_preview_tree_item("绘图快照", FIF.PIE_SINGLE)
        root_item.addChild(snapshot_item)
        snapshot = picture.plot_snapshot
        if snapshot is None:
            snapshot_item.addChild(self._make_preview_tree_item("未保存", getattr(FIF, "INFO", FIF.DOCUMENT)))
        else:
            snapshot_item.addChild(self._make_preview_tree_item(f"主题: {snapshot.figure_state.theme or '-'}", getattr(FIF, "BRUSH", FIF.DOCUMENT)))
            if snapshot.selected_curve_key:
                snapshot_item.addChild(self._make_preview_tree_item(f"当前选中曲线: {snapshot.selected_curve_key}", getattr(FIF, "TARGET", FIF.DOCUMENT)))
            if snapshot.applied_plot_style_ref:
                snapshot_item.addChild(self._make_preview_tree_item(f"绘图样式引用: {snapshot.applied_plot_style_ref}", FIF.PIE_SINGLE))
            if snapshot.active_template_id:
                snapshot_item.addChild(self._make_preview_tree_item(f"模板: {snapshot.active_template_id}", FIF.DOCUMENT))

            series_group = self._make_preview_tree_item(f"曲线 ({len(snapshot.series)})", FIF.PENCIL_INK)
            snapshot_item.addChild(series_group)
            if not snapshot.series:
                series_group.addChild(self._make_preview_tree_item("无", getattr(FIF, "INFO", FIF.DOCUMENT)))
            for series in snapshot.series:
                series_name = series.display_name or series.name or series.curve_key or "未命名曲线"
                series_item = self._make_preview_tree_item(series_name, FIF.PENCIL_INK, series_name)
                series_group.addChild(series_item)
                series_item.addChild(self._make_preview_tree_item(f"点数: {len(series.x)}", getattr(FIF, "INFO", FIF.DOCUMENT)))
                series_item.addChild(self._make_preview_tree_item(f"可见: {'是' if series.visible else '否'}", getattr(FIF, "VIEW", FIF.DOCUMENT)))
                if series.source:
                    series_item.addChild(self._make_preview_tree_item(f"来源: {series.source}", getattr(FIF, "LINK", FIF.DOCUMENT)))

            extension_group = self._make_preview_tree_item(f"绘图扩展 ({len(snapshot.applied_extensions)})", FIF.DEVELOPER_TOOLS)
            snapshot_item.addChild(extension_group)
            if not snapshot.applied_extensions:
                extension_group.addChild(self._make_preview_tree_item("无", getattr(FIF, "INFO", FIF.DOCUMENT)))
            for applied in sorted(snapshot.applied_extensions, key=lambda item: (item.sequence, item.id, item.type)):
                target_name = applied.curve_display_name or applied.curve_name or "全部曲线"
                extension_label = f"{applied.type or '未命名扩展'} -> {target_name}"
                extension_item = self._make_preview_tree_item(extension_label, FIF.DEVELOPER_TOOLS, extension_label)
                extension_group.addChild(extension_item)
                extension_item.addChild(self._make_preview_tree_item(f"参数项: {len(applied.options)}", getattr(FIF, "INFO", FIF.DOCUMENT)))
                if applied.extension_version:
                    extension_item.addChild(self._make_preview_tree_item(f"版本: {applied.extension_version}", getattr(FIF, "INFO", FIF.DOCUMENT)))

        self._picture_preview_tree.expandAll()

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
            f"直接子文件夹: {folder_count}",
            f"源文件: {source_count}",
            f"数据文件: {data_count}",
            f"图像: {image_count}",
            f"分析结果: {analysis_count}",
        ]
        self._show_project_structure_preview(node, title=node.name or "文件夹", summary_lines=preview_lines)

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
        self._data_file_preview_node_id = node_id
        self._set_source_file_preview_mode_controls_visible(False)
        if data_file.series:
            series = data_file.series[0]
            self._selected_type = "series"
            self._selected_id = series.id
            self._restore_plot_type_for_node(node_id)
            self._show_xy_preview(
                series.x,
                series.y,
                series.name or data_file.name or "数据文件",
                series.x_label or "X",
                series.y_label or "Y",
            )
            return True
        preview_text, stats_text = self._build_data_file_parsed_preview(data_file)
        self._show_text_preview(data_file.name or "数据文件", preview_text, stats_text)
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
        state = self._restore_source_file_detail_state(node_id)
        state.last_source_path = str(path)
        stats_lines = [
            f"文件名: {node.name or path.name}",
            f"类型: {path.suffix.lower() or '-'}",
        ]
        try:
            stats_lines.append(f"大小: {self._format_file_size(path.stat().st_size)}")
        except OSError:
            pass

        sheet_names: list[str] = []
        if path.suffix.lower() in {".xlsx", ".xls"}:
            from ui.dialogs.import_dialog import get_excel_sheet_names

            try:
                sheet_names = get_excel_sheet_names(str(path))
            except Exception:
                sheet_names = []
        state.selected_sheet = self._configure_source_file_sheet_options(sheet_names, state.selected_sheet)
        self._configure_source_file_preview_modes(str(path), preferred_mode=state.source_preview_mode)
        state.source_preview_mode = self._current_source_file_preview_mode()
        if self._current_source_file_preview_mode() == "解析" and self._supports_dataset_import(str(path)):
            return self._show_parsed_source_file_preview(
                str(path),
                node.name or path.name,
                stats_lines,
                origin_path=origin_path,
            )

        return self._show_file_preview_from_path(
            str(path),
            node.name or path.name,
            stats_lines,
            origin_path=origin_path,
            show_path_links=True,
            show_source_file_controls=self._supports_dataset_import(str(path)),
        )

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

    def import_current_source_file_to_dataset(self) -> None:
        self._import_current_source_file_to_dataset()

    def _import_current_source_file_to_digitize(self) -> None:
        asset = self._current_source_file_asset()
        source_path = self._current_source_file_path()
        if asset is None or not source_path or not self._supports_digitize_import(source_path):
            InfoBar.warning("提示", "当前源文件类型不支持导入到数字化", parent=self, position=InfoBarPosition.TOP)
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
        InfoBar.success("导入成功", f"已导入到数字化: {asset.name}", parent=self, position=InfoBarPosition.TOP)

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
        elif self._selected_node_kind == "picture":
            node = self._current_tree_node()
            picture_id = getattr(node, "picture_id", None) if node is not None else None
            if picture_id:
                ok = project_manager.rename_picture(picture_id, new_name)
                if ok:
                    node.name = new_name
        elif self._selected_node_kind == "global_extension_config":
            try:
                ok = global_assets.update_extension_config(self._selected_node_id, name=new_name) is not None
            except ValueError as exc:
                InfoBar.warning("重命名失败", str(exc), parent=self, position=InfoBarPosition.TOP)
                return
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
        elif self._selected_node_kind == "picture":
            node = self._current_tree_node()
            picture_id = getattr(node, "picture_id", None) if node is not None else None
            if picture_id:
                ok = project_manager.remove_picture(picture_id) is not None
                if ok:
                    ok = project_manager.delete_node(self._selected_node_id)
        elif self._selected_node_kind == "global_extension_config":
            ok = global_assets.delete_extension_config(self._selected_node_id)
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

    def open_extension_config(self, config_id: str) -> bool:
        self._selected_node_kind = "global_extension_config"
        self._selected_node_id = config_id
        self._selected_type = None
        self._selected_id = None
        if not self._show_extension_config_editor(config_id):
            self._clear_preview()
            self._refresh_management_panel()
            return False
        self._set_actions_enabled(False)
        self._refresh_management_panel()
        return True

    def _create_import_dialog(self, file_path: Optional[str] = None, default_file_name: Optional[str] = None):
        from ui.dialogs.import_dialog import ImportDialog

        dialog = ImportDialog(self)
        if default_file_name:
            dialog.set_default_file_name(default_file_name)
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

        source_path = dialog.get_source_path() if hasattr(dialog, "get_source_path") else ""
        if not isinstance(source_path, str):
            source_path = ""
        data_file = DataFile(
            name=dialog.get_file_name(),
            source_path=source_path,
            series=series_list,
        )
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
            import_name = self._pending_import_names.get(file_path, path.name)
            if not path.exists():
                failed_names.append(import_name)
                continue
            try:
                dialog = self._create_import_dialog(str(path), default_file_name=import_name)
            except Exception as exc:
                failed_names.append(import_name)
                InfoBar.warning("导入失败", f"无法读取文件 {path.name}: {exc}", parent=self, position=InfoBarPosition.TOP)
                continue
            if not dialog.exec():
                stopped = True
                break
            if self._apply_import_dialog_results(dialog, show_feedback=False):
                completed_paths.append(str(path))
            else:
                failed_names.append(import_name)

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

    def _import_pending_source_files_to_datasets_default_mode(self) -> None:
        if not self._pending_import_paths:
            return

        completed_paths: list[str] = []
        failed_names: list[str] = []
        current_selection = (self._selected_node_kind, self._selected_node_id)

        for file_path in list(self._pending_import_paths):
            path = Path(file_path)
            import_name = self._pending_import_names.get(file_path, path.name)
            if not path.exists():
                failed_names.append(import_name)
                continue
            try:
                dialog = self._create_import_dialog(str(path), default_file_name=import_name)
                dialog.import_with_default_options()
            except Exception as exc:
                failed_names.append(import_name)
                InfoBar.warning("导入失败", f"无法按默认模式导入文件 {path.name}: {exc}", parent=self, position=InfoBarPosition.TOP)
                continue
            if self._apply_import_dialog_results(dialog, show_feedback=False):
                completed_paths.append(str(path))
            else:
                failed_names.append(import_name)

        if completed_paths:
            self._remove_pending_source_files(completed_paths)
            self.project_modified.emit()
            self.refresh()
            if current_selection[0] and current_selection[1]:
                self.on_tree_node_selected(current_selection[0], current_selection[1])

        summary = f"成功按默认模式导入 {len(completed_paths)} 个文件到数据集"
        if failed_names:
            summary += f"，失败 {len(failed_names)} 个"
        if completed_paths:
            InfoBar.success("默认模式导入完成", summary, parent=self, position=InfoBarPosition.TOP)
        elif failed_names:
            InfoBar.warning("默认模式导入未完成", summary, parent=self, position=InfoBarPosition.TOP)

    def _import_pending_source_files_to_digitize(self) -> None:
        if not self._pending_import_paths:
            return

        completed_paths: list[str] = []
        skipped_names: list[str] = []
        current_selection = (self._selected_node_kind, self._selected_node_id)

        for file_path in list(self._pending_import_paths):
            path = Path(file_path)
            import_name = self._pending_import_names.get(file_path, path.name)
            if not path.exists():
                skipped_names.append(import_name)
                continue
            if not self._supports_digitize_import(str(path)):
                skipped_names.append(import_name)
                continue
            try:
                project_manager.add_image(str(path), name=import_name)
            except ValueError:
                skipped_names.append(import_name)
                continue
            completed_paths.append(str(path))

        if completed_paths:
            self._remove_pending_source_files(completed_paths)
            self.project_modified.emit()
            self.refresh()
            if current_selection[0] and current_selection[1]:
                self.on_tree_node_selected(current_selection[0], current_selection[1])

        summary = f"成功导入 {len(completed_paths)} 个文件到数字化"
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
            import_name = self._pending_import_names.get(file_path, Path(file_path).name)
            node = project_manager.add_source_file(
                file_path,
                name=import_name,
                parent_id=target_folder_id,
                auto_rename_on_conflict=True,
            )
            if node is not None:
                completed_paths.append(file_path)
            else:
                failed_names.append(import_name)

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

    def import_file_from_shell(self, file_path: Optional[str] = None) -> None:
        self._import_file(file_path)

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

    def add_dataset_from_shell(self) -> None:
        self._add_dataset()

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
            return
        if self._selected_node_kind == "picture" and self._selected_node_id:
            self.send_to_visualize.emit("picture", self._selected_node_id)

    def _send_to_process(self):
        if self._selected_type and self._selected_id:
            self.send_to_process.emit(self._selected_type, self._selected_id)

    def _selected_export_series(self) -> list[DataSeries]:
        project = project_manager.current_project
        if project is None or not self._selected_node_kind or not self._selected_node_id:
            return []
        if self._selected_node_kind == "data_file":
            node = self._current_tree_node()
            if node is None or node.kind != "data_file":
                return []
            data_file = project.find_data_file(node.data_file_id)
            if data_file is None:
                return []
            return [self._clone_series(series) for series in data_file.series]
        if self._selected_node_kind in {"series", "curve"}:
            series = project_manager.get_series_from_node(self._selected_node_kind, self._selected_node_id)
            if series is None:
                return []
            return [self._clone_series(series)]
        return []

    def _default_curve_export_name(self) -> str:
        name = (self._current_node_name() or "data_export").strip()
        name = name.replace("/", "_").replace("\\", "_")
        return name or "data_export"

    @staticmethod
    def _ensure_curve_export_suffix(path_text: str, file_format: str) -> str:
        path = Path(path_text)
        suffix = f".{str(file_format or 'csv').strip().lower()}"
        if path.suffix.lower() == suffix:
            return str(path)
        if path.suffix:
            return str(path.with_suffix(suffix))
        return str(path.with_name(f"{path.name}{suffix}"))

    def _export_csv(self):
        import datetime

        series_list = self._selected_export_series()
        if not series_list:
            InfoBar.warning("提示", "当前节点没有可导出的曲线数据", parent=self, position=InfoBarPosition.TOP)
            return

        merge_supported = False
        if len(series_list) > 1:
            try:
                merge_supported = Exporter.can_merge_data_series(series_list)
            except ValueError:
                merge_supported = False

        export_plan = choose_curve_file_export_plan(
            self,
            title="导出数据",
            source_labels=[series.name or f"series_{index + 1}" for index, series in enumerate(series_list)],
            merge_supported=merge_supported,
        )
        if export_plan is None:
            return

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") if export_plan.include_timestamp else None
        try:
            if export_plan.action == "clipboard":
                Exporter.export_series_to_clipboard(series_list, timestamp=timestamp, merged=export_plan.merged)
                InfoBar.success("已复制", "曲线数据已复制到剪贴板", parent=self, position=InfoBarPosition.TOP)
                return
            default_name = self._ensure_curve_export_suffix(self._default_curve_export_name(), export_plan.file_format)
            path, _ = QFileDialog.getSaveFileName(
                self,
                "导出数据",
                default_name,
                curve_export_file_filter(export_plan.file_format),
            )
            if not path:
                return
            path = self._ensure_curve_export_suffix(path, export_plan.file_format)
            Exporter.export_series_file(series_list, path, fmt=export_plan.file_format, timestamp=timestamp, merged=export_plan.merged)
            InfoBar.success("导出成功", path, parent=self, position=InfoBarPosition.TOP)
        except Exception as exc:
            InfoBar.error("导出失败", str(exc), parent=self, position=InfoBarPosition.TOP)

    # ─────────────────────────────────────────────────────────
    # 主题更新
    # ─────────────────────────────────────────────────────────

    def update_theme(self):
        self._apply_preview_host_background()
        if self._preview_figure is None or self._preview_canvas is None:
            return
        if not self.isVisible():
            self._theme_refresh_pending = True
            return
        self._theme_refresh_pending = False
        QTimer.singleShot(0, self._draw_preview)

    def on_tree_node_selected(self, kind: str, node_id: str) -> None:
        """共享树选中节点 → 显示预览。"""
        self._workspace_controller.handle_tree_selected(kind, node_id)
        if kind == "global_extension_config" and self._show_extension_config_editor(node_id):
            self._selected_type = None
            self._selected_id = None
            self._set_actions_enabled(False)
            self._refresh_management_panel()
            return
        if kind in {"global_pipeline", "global_curve_style_template", "global_plot_style", "global_plot_theme", "global_report_template"} and self._show_global_template_editor(kind, node_id):
            self._selected_type = None
            self._selected_id = None
            self._set_actions_enabled(False)
            self._refresh_management_panel()
            return
        if kind.startswith("global_") and self._show_global_resource_preview(kind, node_id):
            self._selected_type = None
            self._selected_id = None
            self._set_actions_enabled(False)
            self._refresh_management_panel()
            return
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
                self._restore_plot_type_for_node(node_id)
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
        if kind == "picture" and self._show_picture_preview(node_id):
            self._selected_type = None
            self._selected_id = None
            self._set_actions_enabled(False)
            self._btn_to_vis.setEnabled(True)
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
                self._restore_external_browser_dir_for_node(node_id)
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
