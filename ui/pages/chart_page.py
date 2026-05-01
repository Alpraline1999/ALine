"""图表页面 - 共享项目树驱动的可视化。"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import uuid
import warnings
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLayout,
    QListWidgetItem,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    BodyLabel,
    CardWidget,
    CheckBox,
    ColorPickerButton,
    ComboBox,
    FluentIcon as FIF,
    InfoBarIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    ListWidget,
    MessageBox,
    PrimaryPushButton,
    PushButton,
    RoundMenu,
    Slider,
    SmoothScrollArea,
    TabCloseButtonDisplayMode,
    TeachingTip,
    TeachingTipTailPosition,
    TeachingTipView,
    ToolTip,
    ToolButton,
    ToolTipFilter,
    ToolTipPosition,
    isDarkTheme,
)

from core.global_assets import global_assets, make_plot_style_asset_key, parse_plot_style_asset_key
from core.extension_api import (
    PlotExtensionContext,
    build_extension_entry,
    compare_extension_versions,
    extension_registry,
    reload_configured_extensions,
)
from core.extension_runtime import invoke_plot_extension_handler
from core.shortcut_manager import ShortcutBindingSet
from core.rendering import RenderDecimationPolicy, decimate_xy_for_rendering
from core.project_manager import project_manager
from models.schemas import (
    AxisConfig,
    CurveStyle,
    CurveStyleTemplate,
    FigureConfig,
    FigureState,
    PicturePlotExtensionSnapshot,
    PicturePlotExtraVersion,
    PicturePlotSeriesSnapshot,
    PicturePlotSnapshot,
)
from ui.dialogs.export_flow import choose_picture_export_plan
from ui.dialogs.fluent_dialogs import SelectionDialog, TextInputDialog
from ui.matplotlib_fonts import list_matplotlib_font_families
from ui.widgets.extension_panel import ExtensionConfigPanel
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
from ui.widgets.navigation_stack import SegmentedStackWidget
from ui.widgets.onboarding import OnboardingStep, PageOnboardingController
from ui.theme import WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_MIN_WIDTH, WORKBENCH_TOOL_PANEL_WIDTH, apply_button_metrics, install_fluent_tooltip, make_hint_label, make_hsep, make_section_label, preview_canvas_background_color, preview_canvas_foreground_color, preview_canvas_grid_color, secondary_text_style_sheet
from app.workspaces.chart_workspace import ChartWorkspaceController, ChartWorkspaceState
from .page_shell_helpers import ExtensionPanelShellMixin, sync_vertical_splitter_sizes
from ui.page_view_state import ChartPageViewState
from .chart_page_support import (
    HAS_MATPLOTLIB,
    Figure,
    FigureCanvas,
    _BASE_CURVE_STYLE_EXTENSION,
    _BASE_CURVE_STYLE_EXTENSION_TYPE,
    _BASE_PLOT_STYLE_EXTENSION,
    _BASE_PLOT_STYLE_EXTENSION_TYPE,
    _CANVAS_ALPHA_DEFAULT,
    _GRID_ALPHA_DEFAULT,
    _ICON_EXPORT_TO_PICTURES,
    _ICON_HIDE,
    _ICON_SHOW,
    _LEGEND_ALPHA_DEFAULT,
    _MATPLOTLIB_ERROR,
    _PLOT_EXTENSION_TEACHING_TIP_TEXT,
    _STYLE_LABELS,
    _STYLE_LINESTYLES,
    _STYLE_MARKERS,
    _TICK_DIRECTION_CHOICES,
    _THEME_HINTS,
    alpha_from_slider_value,
    alpha_slider_value,
    connect_line_edit_commit,
    make_style_form_label,
    set_compact_edit_width,
    set_square_tool_button,
)

_CHART_RENDER_DECIMATION_POLICY = RenderDecimationPolicy(max_points=2500)


def _merge_nested_mapping(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in dict(patch or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_nested_mapping(result[key], value)
            continue
        result[key] = copy.deepcopy(value)
    return result


def _flatten_nested_mapping(data: Dict[str, Any], prefix: tuple[str, ...] = ()) -> Dict[tuple[str, ...], Any]:
    flattened: Dict[tuple[str, ...], Any] = {}
    for key, value in dict(data or {}).items():
        next_prefix = (*prefix, str(key))
        if isinstance(value, dict):
            if value:
                flattened.update(_flatten_nested_mapping(value, next_prefix))
            else:
                flattened[next_prefix] = {}
            continue
        flattened[next_prefix] = copy.deepcopy(value)
    return flattened


def _nested_mapping_changed_paths(before: Dict[str, Any], after: Dict[str, Any]) -> set[tuple[str, ...]]:
    before_flat = _flatten_nested_mapping(before)
    after_flat = _flatten_nested_mapping(after)
    return {
        path
        for path in set(before_flat) | set(after_flat)
        if before_flat.get(path) != after_flat.get(path)
    }


def _set_nested_mapping_value(target: Dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    if not path:
        return
    current = target
    for segment in path[:-1]:
        child = current.get(segment)
        if not isinstance(child, dict):
            child = {}
            current[segment] = child
        current = child
    current[path[-1]] = copy.deepcopy(value)


class ChartPage(ExtensionPanelShellMixin, QWidget):
    """数据可视化页面。"""

    extensions_reloaded = Signal()
    project_modified = Signal()
    assets_modified = Signal()

    tree_filter_kinds: List[str] = [
        "folder",
        "data_file",
        "image_work",
        "picture",
        "global_curve_style_template",
        "global_plot_style",
        "global_plot_theme",
        "series",
        "curve",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ensure_base_style_extensions_registered()
        self._workspace_state = ChartWorkspaceState()
        self._workspace_controller = ChartWorkspaceController(self._workspace_state)
        self._view_state = ChartPageViewState()
        self._chart_series: List[dict] = []
        self._curve_styles: Dict[str, dict] = {}
        self._style_target: Optional[str] = None
        self._figure_state = FigureState()
        self._plot_style_refs: List[Optional[str]] = [None]
        self._applied_plot_style_ref: Optional[str] = None
        self._active_template_node_id: Optional[str] = None
        self._curve_style_template_ids: List[Optional[str]] = [None]
        self._active_curve_style_ref: Optional[str] = None
        self._active_curve_style_template_id: Optional[str] = None
        self._current_plot_theme_id: Optional[str] = None
        self._plot_extension_options: Dict[str, dict] = {}
        self._applied_plot_extensions: List[Dict[str, Any]] = []
        self._plot_extension_instance_seed = 0
        self._style_change_sequence = 0
        self._figure_state_change_versions: Dict[str, int] = {}
        self._plot_style_extra_versions: Dict[tuple[str, ...], int] = {}
        self._curve_style_change_versions: Dict[str, Dict[str, int]] = {}
        self._plot_style_extras: Dict[str, Any] = {}
        self._legend_anchor_x_draft = ""
        self._legend_anchor_y_draft = ""
        self._preserve_partial_legend_anchor_draft = False
        self._display_dpi = 100.0
        self._display_canvas_size: Optional[tuple[int, int]] = None
        self._canvas_host: Optional[QScrollArea] = None
        self._plot_extension_teaching_tip = None
        self._chart_list_tooltip = None
        self._selected_tree_kind: Optional[str] = None
        self._selected_tree_id: Optional[str] = None
        self._theme_refresh_pending = False
        self._shortcut_bindings = ShortcutBindingSet()

        self._redraw_timer = QTimer(self)
        self._redraw_timer.setSingleShot(True)
        self._redraw_timer.setInterval(250)
        self._redraw_timer.timeout.connect(self._redraw_now)

        self._setup_ui()
        self._setup_shortcuts()
        self._click_away_focus_commit = install_click_away_focus_commit(self)
        self._onboarding_controller = PageOnboardingController(self, "chart", self._chart_onboarding_steps)

    def _ensure_base_style_extensions_registered(self) -> None:
        if extension_registry.get_plot(_BASE_CURVE_STYLE_EXTENSION_TYPE) is None:
            extension_registry.register_plot(_BASE_CURVE_STYLE_EXTENSION)
        if extension_registry.get_plot(_BASE_PLOT_STYLE_EXTENSION_TYPE) is None:
            extension_registry.register_plot(_BASE_PLOT_STYLE_EXTENSION)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._update_plot_extension_help_area_height()
        QTimer.singleShot(0, self._sync_chart_left_splitter_sizes)
        if self._theme_refresh_pending:
            self._theme_refresh_pending = False
            self._redraw_timer.start(0)
        self._onboarding_controller.schedule_auto_start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_plot_extension_help_area_height()
        if not self._view_state.chart_left_splitter_user_resized:
            QTimer.singleShot(0, self._sync_chart_left_splitter_sizes)

    def _sync_chart_left_splitter_sizes(self) -> None:
        sync_vertical_splitter_sizes(
            getattr(self, "_chart_left_splitter", None),
            user_resized=self._view_state.chart_left_splitter_user_resized,
            upper_ratio=0.4,
        )

    def _on_chart_left_splitter_moved(self, _pos: int, _index: int) -> None:
        self._view_state.chart_left_splitter_user_resized = True

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        self._page_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._page_splitter.setHandleWidth(4)
        root.addWidget(self._page_splitter, 1)

        self._content_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._content_splitter.setHandleWidth(4)

        left_card = CardWidget(self)
        self._tool_panel = left_card
        left_card.setFixedWidth(WORKBENCH_TOOL_PANEL_WIDTH)
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(10)

        self._chart_left_splitter = QSplitter(Qt.Orientation.Vertical, left_card)
        self._chart_left_splitter.setHandleWidth(6)
        self._chart_left_splitter.setChildrenCollapsible(False)
        self._chart_left_splitter.splitterMoved.connect(self._on_chart_left_splitter_moved)
        left_layout.addWidget(self._chart_left_splitter, 1)

        list_section = QWidget(self._chart_left_splitter)
                # 先应用扩展 patch，再应用曲线/绘图样式 patch，确保后施加的覆盖先施加的
                # 1. 应用所有扩展 patch 到 context（不直接操作 matplotlib）
                # 2. 再应用曲线样式 patch
                # 3. 再应用绘图样式 patch
        list_layout = QVBoxLayout(list_section)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(10)

        list_layout.addWidget(make_section_label("已绘图曲线", left_card))
        self._chart_list = ListWidget(left_card)
        self._chart_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._chart_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._chart_list.currentItemChanged.connect(self._on_current_changed)
        self._chart_list.customContextMenuRequested.connect(self._on_chart_list_context_menu)
        self._chart_list.viewport().installEventFilter(self)
        list_layout.addWidget(self._chart_list, 1)

        self._chart_path_label = make_hint_label("路径：—", left_card)
        install_fluent_tooltip(self._chart_path_label, delay=300, position=ToolTipPosition.BOTTOM)
        list_layout.addWidget(self._chart_path_label)

        toolbar_row = QHBoxLayout()
        toolbar_row.setContentsMargins(0, 0, 0, 0)
        toolbar_row.setSpacing(8)
        self._btn_clear = PushButton(FIF.DELETE, "清除", left_card)
        self._btn_clear.setToolTip("清除当前画布中的所有曲线")
        self._btn_clear.clicked.connect(self._on_clear_chart)
        apply_button_metrics(self._btn_clear)
        self._btn_clear.setMinimumWidth(0)
        self._btn_clear.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        toolbar_row.addWidget(self._btn_clear)
        self._btn_remove = PushButton(FIF.REMOVE, "移除选中", left_card)
        self._btn_remove.setToolTip("移除当前选中的曲线")
        self._btn_remove.clicked.connect(self._on_remove_selected)
        apply_button_metrics(self._btn_remove, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        toolbar_row.addWidget(self._btn_remove)
        self._btn_selected_up = ToolButton(FIF.UP, left_card)
        self._btn_selected_up.setToolTip("上移")
        self._btn_selected_up.clicked.connect(self._move_selected_curve_up)
        self._set_square_tool_button(self._btn_selected_up)
        toolbar_row.addWidget(self._btn_selected_up)
        self._btn_selected_down = ToolButton(FIF.DOWN, left_card)
        self._btn_selected_down.setToolTip("下移")
        self._btn_selected_down.clicked.connect(self._move_selected_curve_down)
        self._set_square_tool_button(self._btn_selected_down)
        toolbar_row.addWidget(self._btn_selected_down)
        self._btn_toggle_visible = ToolButton(_ICON_HIDE, left_card)
        self._btn_toggle_visible.setToolTip("隐藏当前曲线")
        self._btn_toggle_visible.clicked.connect(self._toggle_selected_visibility)
        self._btn_toggle_visible.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)
        toolbar_row.addWidget(self._btn_toggle_visible)
        toolbar_row.addStretch()
        list_layout.addLayout(toolbar_row)

        style_section = QWidget(self._chart_left_splitter)
        style_layout = QVBoxLayout(style_section)
        style_layout.setContentsMargins(0, 0, 0, 0)
        style_layout.setSpacing(10)

        style_layout.addWidget(make_hsep(left_card))

        self._style_tabs = SegmentedStackWidget(left_card, fill_width=True)
        self._style_tabs.tabBar.setAddButtonVisible(False)
        self._style_tabs.tabBar.setCloseButtonDisplayMode(TabCloseButtonDisplayMode.NEVER)
        self._style_tabs.addTab(self._build_curve_style_tab(left_card), "曲线样式")
        self._style_tabs.addTab(self._build_plot_style_tab(left_card), "绘图样式")
        self._style_tabs.addTab(self._build_plot_extension_tab(left_card), "绘图扩展")
        style_layout.addWidget(self._style_tabs, 1)

        style_layout.addWidget(make_hsep(left_card))
        self._plot_actions_bar = QWidget(left_card)
        plot_actions_layout = QGridLayout(self._plot_actions_bar)
        plot_actions_layout.setContentsMargins(0, 0, 0, 0)
        plot_actions_layout.setHorizontalSpacing(6)
        plot_actions_layout.setVerticalSpacing(4)
        self._btn_export = PushButton(FIF.SHARE, "导出图片", self._plot_actions_bar)
        self._btn_export.clicked.connect(self._on_export_image)
        apply_button_metrics(self._btn_export, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        plot_actions_layout.addWidget(self._btn_export, 0, 0)
        self._btn_export_to_pictures = PrimaryPushButton(_ICON_EXPORT_TO_PICTURES, "导出到图片集", self._plot_actions_bar)
        self._btn_export_to_pictures.clicked.connect(self._on_export_to_picture_group)
        apply_button_metrics(self._btn_export_to_pictures, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        plot_actions_layout.addWidget(self._btn_export_to_pictures, 0, 1)
        plot_actions_layout.setColumnStretch(0, 1)
        plot_actions_layout.setColumnStretch(1, 1)
        style_layout.addWidget(self._plot_actions_bar)
        self._chart_left_splitter.setStretchFactor(0, 0)
        self._chart_left_splitter.setStretchFactor(1, 1)
        self._chart_left_splitter.setSizes([400, 600])

        self._content_splitter.addWidget(left_card)

        right_card = CardWidget(self)
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(14, 14, 14, 14)
        right_layout.setSpacing(10)
        right_layout.addWidget(make_section_label("绘图预览", right_card))
        self._chart_preview_nav_toolbar = None
        self._canvas_host = QScrollArea(right_card)
        self._canvas_host.setFrameShape(QScrollArea.Shape.NoFrame)
        self._canvas_host.setWidgetResizable(True)
        self._canvas_host.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._canvas_host.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        canvas_stage = QWidget(self._canvas_host)
        canvas_stage.setMinimumSize(0, 0)
        self._canvas_host.setWidget(canvas_stage)
        canvas_host_layout = QVBoxLayout(canvas_stage)
        canvas_host_layout.setContentsMargins(0, 0, 0, 0)
        canvas_host_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if HAS_MATPLOTLIB:
            self._figure = Figure(
                figsize=(self._figure_state.figure_width, self._figure_state.figure_height),
                dpi=self._display_dpi,
            )
            self._canvas = FigureCanvas(self._figure)
            self._chart_preview_nav_toolbar = create_navigation_toolbar(
                self._canvas,
                right_card,
                sync_callback=self._sync_chart_preview_nav_toggle_states,
            )
            preview_toolbar, preview_buttons = build_preview_toolbar(
                right_card,
                button_size=WORKBENCH_BUTTON_HEIGHT,
                reset_callback=self._reset_chart_preview_view,
                zoom_in_callback=lambda: self._zoom_chart_preview_axes(0.8),
                zoom_out_callback=lambda: self._zoom_chart_preview_axes(1.25),
                pan_toggle_callback=self._toggle_chart_preview_pan_mode,
                box_zoom_toggle_callback=self._toggle_chart_preview_box_zoom_mode,
                install_tooltip=lambda widget, text: install_fluent_tooltip(widget, delay=300, position=ToolTipPosition.BOTTOM),
            )
            self._chart_preview_fit_btn = preview_buttons.fit
            self._chart_preview_zoom_in_btn = preview_buttons.zoom_in
            self._chart_preview_zoom_out_btn = preview_buttons.zoom_out
            self._chart_preview_pan_btn = preview_buttons.pan
            self._chart_preview_box_zoom_btn = preview_buttons.box_zoom
            right_layout.addLayout(preview_toolbar)
            self._canvas.setMinimumSize(1, 1)
            canvas_host_layout.addWidget(self._canvas, 0, Qt.AlignmentFlag.AlignCenter)
            self._canvas_host.viewport().installEventFilter(self)
            right_layout.addWidget(self._canvas_host, 1)
            self._sync_chart_preview_nav_toggle_states()
        else:
            message = f"matplotlib 加载失败：{_MATPLOTLIB_ERROR}" if _MATPLOTLIB_ERROR else "请安装 matplotlib"
            label = BodyLabel(message, self)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            canvas_host_layout.addWidget(label)
            right_layout.addWidget(self._canvas_host, 1)
            self._figure = None
            self._canvas = None
        self._content_splitter.addWidget(right_card)
        self._content_splitter.setStretchFactor(0, 0)
        self._content_splitter.setStretchFactor(1, 1)
        self._content_splitter.setSizes([340, 980])
        self._page_splitter.addWidget(self._content_splitter)

        self._extension_panel = self._build_plot_extension_side_panel(self)
        self._extension_panel.setMinimumWidth(self._view_state.extension_panel_width)
        self._extension_panel.setMaximumWidth(self._view_state.extension_panel_width)
        self._page_splitter.addWidget(self._extension_panel)
        self._page_splitter.setStretchFactor(0, 1)
        self._page_splitter.setStretchFactor(1, 0)

        self._refresh_curve_style_template_combo()
        self._refresh_template_combo()
        self._style_tabs.stackedWidget.currentChanged.connect(self._refresh_style_extension_panel)
        self._refresh_style_extension_panel()
        self._apply_figure_state(self._figure_state)
        self._apply_preview_host_background()
        self._update_color_btn("#888888")
        self._update_visibility_button()
        self._install_tooltip_filters()
        self.set_extension_panel_visible(self._view_state.extension_panel_visible)

    def _setup_shortcuts(self) -> None:
        context = Qt.ShortcutContext.WidgetWithChildrenShortcut
        self._shortcut_bindings.bind("chart_save_template", self, self._on_save_template, context=context)
        self._shortcut_bindings.bind("chart_save_curve_style_template", self, self._on_save_curve_style_template, context=context)
        self._shortcut_bindings.bind("chart_export_picture", self, self._on_export_to_picture_group, context=context)

    def apply_shortcuts(self) -> None:
        self._shortcut_bindings.apply()

    def start_onboarding(self, force: bool = False) -> None:
        self._onboarding_controller.start(force=force)

    def _chart_onboarding_steps(self) -> List[OnboardingStep]:
        return [
            OnboardingStep(
                lambda: self._chart_list,
                TeachingTipTailPosition.BOTTOM,
                "先看当前曲线",
                "共享树双击数据后，曲线会进入这里；当前选中项也是样式和扩展的默认目标。",
            ),
            OnboardingStep(
                lambda: self._style_tabs,
                TeachingTipTailPosition.BOTTOM,
                "样式与扩展分开管理",
                "左侧保留曲线样式、绘图样式和绘图扩展三个页签；右侧仅保留绘图扩展说明和已加载实例。",
            ),
            OnboardingStep(
                lambda: self._plot_actions_bar,
                TeachingTipTailPosition.LEFT_BOTTOM,
                "导出入口集中在这里",
                "出图后可直接导出，或一键落到项目图片集。",
            ),
            OnboardingStep(
                lambda: self._canvas_host,
                TeachingTipTailPosition.LEFT_BOTTOM,
                "右侧就是最终预览",
                "样式、扩展和图例名调整都会立即反映在这里。",
            ),
        ]

    def _clear_plot_extension_teaching_tip(self) -> None:
        tip = self._plot_extension_teaching_tip
        self._plot_extension_teaching_tip = None
        if tip is not None:
            tip.close()

    def _show_plot_extension_teaching_tip(self) -> None:
        target = getattr(self, "_plot_extension_help_btn", None)
        if target is None:
            return
        self._clear_plot_extension_teaching_tip()
        view = TeachingTipView(
            title="绘图扩展",
            content=_PLOT_EXTENSION_TEACHING_TIP_TEXT,
            icon=InfoBarIcon.INFORMATION,
            isClosable=True,
            tailPosition=TeachingTipTailPosition.BOTTOM,
        )
        view.closed.connect(self._clear_plot_extension_teaching_tip)
        self._plot_extension_teaching_tip = TeachingTip.make(
            view,
            target,
            -1,
            TeachingTipTailPosition.BOTTOM,
            self,
        )

    def _extension_panel_splitter(self) -> QSplitter | None:
        return getattr(self, "_page_splitter", None)

    def _extension_panel_visible_sizes(self) -> tuple[int, int]:
        return (
            max(self.width() - self._view_state.extension_panel_width - 24, 760),
            self._view_state.extension_panel_width,
        )

    def _extension_panel_hidden_sizes(self) -> tuple[int, int]:
        return (1, 0)

    def _chart_preview_navigation_mode(self) -> str:
        return preview_navigation_mode(getattr(self, "_chart_preview_nav_toolbar", None))

    def _sync_chart_preview_nav_toggle_states(self) -> None:
        sync_preview_nav_toggle_states(
            getattr(self, "_chart_preview_nav_toolbar", None),
            getattr(self, "_chart_preview_pan_btn", None),
            getattr(self, "_chart_preview_box_zoom_btn", None),
        )

    def _toggle_chart_preview_pan_mode(self, checked: bool) -> None:
        toggle_preview_pan_mode(
            getattr(self, "_chart_preview_nav_toolbar", None),
            getattr(self, "_chart_preview_pan_btn", None),
            getattr(self, "_chart_preview_box_zoom_btn", None),
            checked,
        )

    def _toggle_chart_preview_box_zoom_mode(self, checked: bool) -> None:
        toggle_preview_box_zoom_mode(
            getattr(self, "_chart_preview_nav_toolbar", None),
            getattr(self, "_chart_preview_pan_btn", None),
            getattr(self, "_chart_preview_box_zoom_btn", None),
            checked,
        )

    def _zoom_chart_preview_axes(self, factor: float) -> None:
        zoom_figure_axes(self._figure, self._canvas, factor, redraw_callback=self._redraw_now)

    def _reset_chart_preview_view(self) -> None:
        self._redraw_now()
        self._sync_chart_preview_nav_toggle_states()

    def _apply_preview_host_background(self) -> None:
        if self._canvas_host is None:
            return
        background = preview_canvas_background_color(isDarkTheme())
        self._canvas_host.setStyleSheet(f"QScrollArea {{ background: {background}; border: none; }}")
        self._canvas_host.viewport().setStyleSheet(f"background: {background};")
        canvas_stage = self._canvas_host.widget()
        if canvas_stage is not None:
            canvas_stage.setStyleSheet(f"background: {background};")

    def _update_extension_remove_action(self) -> None:
        if hasattr(self, "_remove_selected_plot_extension_btn"):
            self._remove_selected_plot_extension_btn.setEnabled(self._selected_plot_extension_instance() is not None)

    def _on_chart_extension_remove_requested(self, type_id: str) -> None:
        applied = next((entry for entry in reversed(self._applied_plot_extensions) if entry.get("type") == type_id), None)
        if applied is None:
            return
        self._remove_plot_extension_instance(str(applied.get("id") or ""))

    def eventFilter(self, watched, event):
        if self._canvas_host is not None and watched is self._canvas_host.viewport() and event.type() == QEvent.Type.Resize:
            self._sync_canvas_display_geometry()
        if hasattr(self, "_chart_list") and watched is self._chart_list.viewport():
            if event.type() == QEvent.Type.ToolTip:
                item = self._chart_list.itemAt(event.position().toPoint() if hasattr(event, "position") else event.pos())
                tooltip_text = item.toolTip().strip() if item is not None else ""
                self._show_chart_list_tooltip(tooltip_text, event)
                return True
            if event.type() in {
                QEvent.Type.Leave,
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseButtonDblClick,
            }:
                self._hide_chart_list_tooltip()
        return super().eventFilter(watched, event)

    def _install_tooltip_filters(self) -> None:
        for widget in self.findChildren(QWidget):
            if widget.toolTip():
                widget.installEventFilter(ToolTipFilter(widget, 500, ToolTipPosition.TOP))

    @staticmethod
    def _set_compact_edit_width(edit: LineEdit, width: int = 96) -> None:
        set_compact_edit_width(edit, width)

    @staticmethod
    def _connect_line_edit_commit(edit: LineEdit, slot) -> None:
        connect_line_edit_commit(edit, slot)

    @staticmethod
    def _alpha_slider_value(alpha: float) -> int:
        return alpha_slider_value(_clamp_float(alpha, 0.0, 1.0))

    @staticmethod
    def _alpha_from_slider_value(value: int) -> float:
        return _clamp_float(alpha_from_slider_value(value), 0.0, 1.0)

    def _update_style_opacity_value_label(self, value: Optional[int] = None) -> None:
        if not hasattr(self, "_style_opacity_value_label"):
            return
        slider_value = self._style_opacity_slider.value() if value is None else value
        self._style_opacity_value_label.setText(f"{self._alpha_from_slider_value(slider_value):.2f}")

    def _update_alpha_value_label(self, label: Optional[BodyLabel], value: int) -> None:
        if label is None:
            return
        label.setText(f"{self._alpha_from_slider_value(value):.2f}")

    def _set_alpha_slider_value(
        self,
        slider: Slider,
        label: Optional[BodyLabel],
        alpha: Optional[float],
        *,
        default_alpha: float,
    ) -> None:
        slider.blockSignals(True)
        slider.setValue(self._alpha_slider_value(default_alpha if alpha is None else alpha))
        slider.blockSignals(False)
        self._update_alpha_value_label(label, slider.value())

    def _on_legend_frame_alpha_changed(self, value: int) -> None:
        self._update_alpha_value_label(getattr(self, "_legend_frame_alpha_value_label", None), value)
        self._on_quick_config_changed()

    def _on_legend_face_alpha_changed(self, value: int) -> None:
        self._update_alpha_value_label(getattr(self, "_legend_face_alpha_value_label", None), value)
        self._on_quick_config_changed()

    def _on_canvas_alpha_changed(self, value: int) -> None:
        self._update_alpha_value_label(getattr(self, "_canvas_alpha_value_label", None), value)
        self._on_quick_config_changed()

    def _on_grid_alpha_changed(self, value: int) -> None:
        self._update_alpha_value_label(getattr(self, "_grid_alpha_value_label", None), value)
        self._on_quick_config_changed()

    def _on_legend_anchor_x_text_changed(self, text: str) -> None:
        self._legend_anchor_x_draft = text.strip()

    def _on_legend_anchor_y_text_changed(self, text: str) -> None:
        self._legend_anchor_y_draft = text.strip()

    def _on_legend_anchor_x_committed(self) -> None:
        self._legend_anchor_x_draft = self._legend_anchor_x_edit.text().strip()
        self._on_quick_config_changed()

    def _on_legend_anchor_y_committed(self) -> None:
        self._legend_anchor_y_draft = self._legend_anchor_y_edit.text().strip()
        self._on_quick_config_changed()

    @staticmethod
    def _set_square_tool_button(button: ToolButton) -> None:
        set_square_tool_button(button, WORKBENCH_BUTTON_HEIGHT)

    @staticmethod
    def _make_style_form_label(text: str, parent: Optional[QWidget] = None, *, minimum_width: int = 0) -> BodyLabel:
        return make_style_form_label(text, parent, minimum_width=minimum_width)

    def _create_style_tab_page(self, parent: QWidget) -> tuple[SmoothScrollArea, QWidget, QVBoxLayout]:
        scroll = SmoothScrollArea(parent)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("SmoothScrollArea { background: transparent; border: none; }")
        page = QWidget(scroll)
        page.setStyleSheet("background: transparent;")
        page.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        scroll.setWidget(page)
        return scroll, page, layout

    def _build_plot_extension_side_panel(self, parent: QWidget) -> QWidget:
        panel = ExtensionConfigPanel("绘图扩展", "应用扩展", parent, mode="help_only", framed=True)
        panel.set_status_context("plot", "绘图扩展")
        panel.set_help_area_layout(expanding=False, min_height=124, max_height=124)

        loaded_section = QWidget(panel)
        loaded_layout = QVBoxLayout(loaded_section)
        loaded_layout.setContentsMargins(0, 0, 0, 0)
        loaded_layout.setSpacing(8)
        loaded_layout.addWidget(make_hsep(loaded_section))

        applied_header = QHBoxLayout()
        applied_header.setContentsMargins(0, 0, 0, 0)
        applied_header.setSpacing(6)
        applied_header.addWidget(make_section_label("已加载扩展", loaded_section))
        applied_header.addStretch()
        self._clear_all_plot_extensions_btn = ToolButton(FIF.DELETE, loaded_section)
        self._set_square_tool_button(self._clear_all_plot_extensions_btn)
        self._clear_all_plot_extensions_btn.setToolTip("清除全部已加载扩展")
        self._clear_all_plot_extensions_btn.clicked.connect(self._clear_all_plot_extensions)
        self._clear_all_plot_extensions_btn.installEventFilter(ToolTipFilter(self._clear_all_plot_extensions_btn, 300, ToolTipPosition.TOP))
        self._clear_all_plot_extensions_btn.setEnabled(False)
        applied_header.addWidget(self._clear_all_plot_extensions_btn)
        self._remove_selected_plot_extension_btn = PushButton("撤销选中", loaded_section)
        self._remove_selected_plot_extension_btn.clicked.connect(self._remove_selected_plot_extension)
        self._remove_selected_plot_extension_btn.setEnabled(False)
        applied_header.addWidget(self._remove_selected_plot_extension_btn)
        loaded_layout.addLayout(applied_header)

        self._plot_extension_repeat_hint = make_hint_label("同一扩展可重复加载，列表会保留目标曲线和参数摘要。", loaded_section)
        loaded_layout.addWidget(self._plot_extension_repeat_hint)

        self._plot_extension_applied_list = ListWidget(loaded_section)
        self._plot_extension_applied_list.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._plot_extension_applied_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._plot_extension_applied_list.currentItemChanged.connect(self._on_plot_extension_instance_selection_changed)
        loaded_layout.addWidget(self._plot_extension_applied_list, 1)

        panel.add_bottom_widget(loaded_section, stretch=1)
        return panel

    def _update_plot_extension_help_area_height(self) -> None:
        if not hasattr(self, "_extension_panel") or not isinstance(self._extension_panel, ExtensionConfigPanel):
            return
        panel_height = max(int(self._extension_panel.height() or 0), 0)
        target_height = max(124, panel_height // 3) if panel_height else 124
        self._extension_panel.set_help_area_layout(expanding=False, min_height=target_height, max_height=target_height)

    def _update_plot_extension_info_panel(self, type_id: Optional[str]) -> None:
        if not hasattr(self, "_extension_panel") or not isinstance(self._extension_panel, ExtensionConfigPanel):
            return
        self._extension_panel.set_entries(
            self._plot_extension_entries(),
            saved_options=self._plot_extension_options,
            current_type=type_id,
        )

    def _on_plot_extension_type_changed(self, type_id: str) -> None:
        self._update_plot_extension_info_panel(type_id or None)
        self._update_extension_remove_action()

    def _build_curve_style_tab(self, parent: QWidget) -> QWidget:
        scroll, page, layout = self._create_style_tab_page(parent)

        self._curve_style_template_label = make_hint_label("当前曲线样式未绑定全局模板。", page)
        layout.addWidget(self._curve_style_template_label)
        self._curve_style_template_label.hide()

        curve_template_row = QHBoxLayout()
        curve_template_row.setContentsMargins(0, 0, 0, 0)
        curve_template_row.setSpacing(6)
        self._curve_style_template_combo = ComboBox(page)
        self._curve_style_template_combo.currentIndexChanged.connect(self._on_curve_style_template_selected)
        curve_template_row.addWidget(self._curve_style_template_combo, 1)
        self._btn_load_curve_style_template = ToolButton(FIF.FOLDER, page)
        self._btn_load_curve_style_template.setToolTip("加载选中的全局曲线样式")
        self._btn_load_curve_style_template.clicked.connect(self._load_selected_curve_style_template)
        self._set_square_tool_button(self._btn_load_curve_style_template)
        curve_template_row.addWidget(self._btn_load_curve_style_template)
        self._btn_save_curve_style_template = ToolButton(FIF.ADD, page)
        self._btn_save_curve_style_template.setToolTip("将当前曲线样式另存为全局样式")
        self._btn_save_curve_style_template.clicked.connect(self._on_save_curve_style_template)
        self._set_square_tool_button(self._btn_save_curve_style_template)
        curve_template_row.addWidget(self._btn_save_curve_style_template)
        self._btn_update_curve_style_template = ToolButton(FIF.SAVE, page)
        self._btn_update_curve_style_template.setToolTip("覆盖当前全局曲线样式")
        self._btn_update_curve_style_template.clicked.connect(self._on_update_curve_style_template)
        self._set_square_tool_button(self._btn_update_curve_style_template)
        curve_template_row.addWidget(self._btn_update_curve_style_template)
        layout.addLayout(curve_template_row)

        layout.addWidget(make_hsep(page))
        self._style_target_label = make_hint_label("当前选中：未选中", page)
        layout.addWidget(self._style_target_label)
        self._style_target_label.hide()

        layout.addWidget(make_hsep(page))
        layout.addWidget(make_section_label("基础外观", page))

        color_row = QHBoxLayout()
        color_row.addWidget(self._make_style_form_label("颜色:", page))
        self._style_color_btn = ColorPickerButton(QColor("#888888"), "", page, enableAlpha=False)
        self._style_color_btn.setToolTip("当前曲线颜色")
        self._style_color_btn.setFixedSize(32, 32)
        self._style_color_btn.setEnabled(False)
        self._style_color_btn.colorChanged.connect(self._on_style_color_changed)
        color_row.addWidget(self._style_color_btn)
        self._style_reset_color_btn = ToolButton(FIF.CANCEL, page)
        self._style_reset_color_btn.setToolTip("恢复原始曲线颜色")
        self._style_reset_color_btn.setEnabled(False)
        self._style_reset_color_btn.clicked.connect(self._on_style_reset_color)
        self._set_square_tool_button(self._style_reset_color_btn)
        color_row.addWidget(self._style_reset_color_btn)
        color_row.addWidget(self._make_style_form_label("线型:", page))
        self._style_line_combo = ComboBox(page)
        self._style_line_combo.addItems(_STYLE_LABELS)
        self._style_line_combo.setEnabled(False)
        self._style_line_combo.currentIndexChanged.connect(self._on_style_line_changed)
        color_row.addWidget(self._style_line_combo, 1)
        layout.addLayout(color_row)

        layout.addWidget(make_hsep(page))
        layout.addWidget(make_section_label("线条细节", page))

        line_metric_row = QHBoxLayout()
        line_metric_row.addWidget(self._make_style_form_label("线宽:", page))
        self._style_line_width_edit = LineEdit(page)
        self._style_line_width_edit.setPlaceholderText("1.4")
        self._style_line_width_edit.setEnabled(False)
        self._connect_line_edit_commit(self._style_line_width_edit, self._on_style_metrics_changed)
        self._set_compact_edit_width(self._style_line_width_edit)
        line_metric_row.addWidget(self._style_line_width_edit)
        line_metric_row.addStretch()
        layout.addLayout(line_metric_row)

        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self._make_style_form_label("透明度:", page))
        self._style_opacity_slider = Slider(Qt.Orientation.Horizontal, page)
        self._style_opacity_slider.setRange(0, 100)
        self._style_opacity_slider.setSingleStep(1)
        self._style_opacity_slider.setPageStep(5)
        self._style_opacity_slider.setEnabled(False)
        self._style_opacity_slider.setMinimumWidth(152)
        self._style_opacity_slider.setValue(self._alpha_slider_value(1.0))
        opacity_row.addWidget(self._style_opacity_slider, 1)
        self._style_opacity_value_label = BodyLabel("1.00", page)
        self._style_opacity_value_label.setStyleSheet(secondary_text_style_sheet(font_size=12))
        self._style_opacity_value_label.setMinimumWidth(40)
        opacity_row.addWidget(self._style_opacity_value_label)
        opacity_row.addStretch()
        self._update_style_opacity_value_label(self._style_opacity_slider.value())
        self._style_opacity_slider.valueChanged.connect(self._on_style_opacity_changed)
        layout.addLayout(opacity_row)

        dash_scale_row = QHBoxLayout()
        dash_scale_row.addWidget(self._make_style_form_label("虚线缩放:", page))
        self._style_dash_scale_edit = LineEdit(page)
        self._style_dash_scale_edit.setPlaceholderText("1.0")
        self._style_dash_scale_edit.setEnabled(False)
        self._connect_line_edit_commit(self._style_dash_scale_edit, self._on_style_metrics_changed)
        self._set_compact_edit_width(self._style_dash_scale_edit)
        dash_scale_row.addWidget(self._style_dash_scale_edit)
        dash_scale_row.addStretch()
        layout.addLayout(dash_scale_row)

        layout.addWidget(make_hsep(page))
        layout.addWidget(make_section_label("标记与可见性", page))

        marker_set_row = QHBoxLayout()
        marker_set_row.addWidget(self._make_style_form_label("点大小:", page))
        self._style_marker_size_edit = LineEdit(page)
        self._style_marker_size_edit.setPlaceholderText("5.0")
        self._style_marker_size_edit.setEnabled(False)
        self._connect_line_edit_commit(self._style_marker_size_edit, self._on_style_metrics_changed)
        self._set_compact_edit_width(self._style_marker_size_edit)
        marker_set_row.addWidget(self._style_marker_size_edit)

        marker_set_row.addWidget(self._make_style_form_label("点间距:", page))
        self._style_density_edit = LineEdit(page)
        self._style_density_edit.setPlaceholderText("1")
        self._style_density_edit.setEnabled(False)
        self._connect_line_edit_commit(self._style_density_edit, self._on_style_metrics_changed)
        self._set_compact_edit_width(self._style_density_edit)
        marker_set_row.addWidget(self._style_density_edit)
        marker_set_row.addStretch()
        layout.addLayout(marker_set_row)

        visibility_row = QHBoxLayout()
        self._style_visible_cb = CheckBox("显示当前曲线", page)
        self._style_visible_cb.setEnabled(False)
        self._style_visible_cb.stateChanged.connect(self._on_style_visibility_changed)
        visibility_row.addWidget(self._style_visible_cb)
        visibility_row.addStretch()
        layout.addLayout(visibility_row)

        layout.addStretch()
        return scroll

    def _build_plot_style_tab(self, parent: QWidget) -> QWidget:
        scroll, page, layout = self._create_style_tab_page(parent)
        self._plot_style_scroll = scroll

        self._template_summary_label = make_hint_label("当前为临时绘图样式。", page)
        layout.addWidget(self._template_summary_label)
        self._template_summary_label.hide()

        template_row = QHBoxLayout()
        template_row.setContentsMargins(0, 0, 0, 0)
        template_row.setSpacing(6)
        self._template_combo = ComboBox(page)
        self._template_combo.currentIndexChanged.connect(self._on_template_selected)
        template_row.addWidget(self._template_combo, 1)
        self._btn_load_template = ToolButton(FIF.FOLDER, page)
        self._btn_load_template.setToolTip("加载当前选中的绘图样式")
        self._btn_load_template.clicked.connect(self._load_selected_plot_style)
        self._set_square_tool_button(self._btn_load_template)
        template_row.addWidget(self._btn_load_template)
        self._btn_save_template = ToolButton(FIF.ADD, page)
        self._btn_save_template.setToolTip("将当前绘图样式另存为全局样式")
        self._btn_save_template.clicked.connect(self._on_save_template)
        self._set_square_tool_button(self._btn_save_template)
        template_row.addWidget(self._btn_save_template)
        self._btn_update_template = ToolButton(FIF.SAVE, page)
        self._btn_update_template.setToolTip("覆盖当前已保存绘图样式")
        self._btn_update_template.clicked.connect(self._on_update_template)
        self._set_square_tool_button(self._btn_update_template)
        template_row.addWidget(self._btn_update_template)
        layout.addLayout(template_row)

        self._theme_hint_label = make_hint_label("", page)
        layout.addWidget(self._theme_hint_label)
        self._theme_hint_label.hide()

        layout.addWidget(make_hsep(page))
        layout.addWidget(make_section_label("基础配置", page))

        x_row = QHBoxLayout()
        x_row.addWidget(self._make_style_form_label("X:", page))
        self._x_label_edit = LineEdit(page)
        self._x_label_edit.setPlaceholderText("X")
        self._connect_line_edit_commit(self._x_label_edit, self._on_quick_config_changed)
        x_row.addWidget(self._x_label_edit)
        layout.addLayout(x_row)

        y_row = QHBoxLayout()
        y_row.addWidget(self._make_style_form_label("Y:", page))
        self._y_label_edit = LineEdit(page)
        self._y_label_edit.setPlaceholderText("Y")
        self._connect_line_edit_commit(self._y_label_edit, self._on_quick_config_changed)
        y_row.addWidget(self._y_label_edit)
        layout.addLayout(y_row)

        self._errbar_cb = CheckBox("显示误差棒", page)
        self._errbar_cb.stateChanged.connect(self._on_quick_config_changed)
        layout.addWidget(self._errbar_cb)

        layout.addWidget(make_hsep(page))
        layout.addWidget(make_section_label("坐标轴", page))

        x_range_row = QHBoxLayout()
        x_range_row.addWidget(self._make_style_form_label("X 最小:", page))
        self._x_min_edit = LineEdit(page)
        self._x_min_edit.setPlaceholderText("自动")
        self._connect_line_edit_commit(self._x_min_edit, self._on_quick_config_changed)
        self._set_compact_edit_width(self._x_min_edit)
        x_range_row.addWidget(self._x_min_edit)
        x_range_row.addWidget(self._make_style_form_label("最大:", page))
        self._x_max_edit = LineEdit(page)
        self._x_max_edit.setPlaceholderText("自动")
        self._connect_line_edit_commit(self._x_max_edit, self._on_quick_config_changed)
        self._set_compact_edit_width(self._x_max_edit)
        x_range_row.addWidget(self._x_max_edit)
        layout.addLayout(x_range_row)

        y_range_row = QHBoxLayout()
        y_range_row.addWidget(self._make_style_form_label("Y 最小:", page))
        self._y_min_edit = LineEdit(page)
        self._y_min_edit.setPlaceholderText("自动")
        self._connect_line_edit_commit(self._y_min_edit, self._on_quick_config_changed)
        self._set_compact_edit_width(self._y_min_edit)
        y_range_row.addWidget(self._y_min_edit)
        y_range_row.addWidget(self._make_style_form_label("最大:", page))
        self._y_max_edit = LineEdit(page)
        self._y_max_edit.setPlaceholderText("自动")
        self._connect_line_edit_commit(self._y_max_edit, self._on_quick_config_changed)
        self._set_compact_edit_width(self._y_max_edit)
        y_range_row.addWidget(self._y_max_edit)
        layout.addLayout(y_range_row)

        axis_flag_row = QHBoxLayout()
        self._x_log_cb = CheckBox("X 对数坐标", page)
        self._x_log_cb.stateChanged.connect(self._on_quick_config_changed)
        axis_flag_row.addWidget(self._x_log_cb)
        self._y_log_cb = CheckBox("Y 对数坐标", page)
        self._y_log_cb.stateChanged.connect(self._on_quick_config_changed)
        axis_flag_row.addWidget(self._y_log_cb)
        axis_flag_row.addStretch()
        layout.addLayout(axis_flag_row)

        layout.addWidget(make_hsep(page))
        layout.addWidget(make_section_label("刻度", page))

        tick_side_1_row = QHBoxLayout()
        self._tick_bottom_cb = CheckBox("底部刻度", page)
        self._tick_bottom_cb.setChecked(True)
        self._tick_bottom_cb.stateChanged.connect(self._on_quick_config_changed)
        tick_side_1_row.addWidget(self._tick_bottom_cb)
        self._tick_left_cb = CheckBox("左侧刻度", page)
        self._tick_left_cb.setChecked(True)
        self._tick_left_cb.stateChanged.connect(self._on_quick_config_changed)
        tick_side_1_row.addWidget(self._tick_left_cb)
        tick_side_1_row.addStretch()
        layout.addLayout(tick_side_1_row)

        tick_side_2_row = QHBoxLayout()
        self._tick_top_cb = CheckBox("顶部刻度", page)
        self._tick_top_cb.stateChanged.connect(self._on_quick_config_changed)
        tick_side_2_row.addWidget(self._tick_top_cb)
        self._tick_right_cb = CheckBox("右侧刻度", page)
        self._tick_right_cb.stateChanged.connect(self._on_quick_config_changed)
        tick_side_2_row.addWidget(self._tick_right_cb)
        tick_side_2_row.addStretch()
        layout.addLayout(tick_side_2_row)

        tick_label_toggle_1_row = QHBoxLayout()
        self._tick_label_bottom_cb = CheckBox("底部标签", page)
        self._tick_label_bottom_cb.setChecked(True)
        self._tick_label_bottom_cb.stateChanged.connect(self._on_quick_config_changed)
        tick_label_toggle_1_row.addWidget(self._tick_label_bottom_cb)
        self._tick_label_left_cb = CheckBox("左侧标签", page)
        self._tick_label_left_cb.setChecked(True)
        self._tick_label_left_cb.stateChanged.connect(self._on_quick_config_changed)
        tick_label_toggle_1_row.addWidget(self._tick_label_left_cb)
        tick_label_toggle_1_row.addStretch()
        layout.addLayout(tick_label_toggle_1_row)

        tick_label_toggle_2_row = QHBoxLayout()
        self._tick_label_top_cb = CheckBox("顶部标签", page)
        self._tick_label_top_cb.stateChanged.connect(self._on_quick_config_changed)
        tick_label_toggle_2_row.addWidget(self._tick_label_top_cb)
        self._tick_label_right_cb = CheckBox("右侧标签", page)
        self._tick_label_right_cb.stateChanged.connect(self._on_quick_config_changed)
        tick_label_toggle_2_row.addWidget(self._tick_label_right_cb)
        tick_label_toggle_2_row.addStretch()
        layout.addLayout(tick_label_toggle_2_row)

        tick_direction_row = QHBoxLayout()
        tick_direction_row.addWidget(self._make_style_form_label("方向:", page))
        self._tick_direction_combo = ComboBox(page)
        self._tick_direction_combo.addItems(_TICK_DIRECTION_CHOICES)
        self._tick_direction_combo.currentIndexChanged.connect(self._on_quick_config_changed)
        tick_direction_row.addWidget(self._tick_direction_combo, 1)
        layout.addLayout(tick_direction_row)

        tick_label_row = QHBoxLayout()
        tick_label_row.addWidget(self._make_style_form_label("标签字号:", page))
        self._tick_label_size_edit = LineEdit(page)
        self._tick_label_size_edit.setPlaceholderText("跟随字号")
        self._connect_line_edit_commit(self._tick_label_size_edit, self._on_quick_config_changed)
        self._set_compact_edit_width(self._tick_label_size_edit)
        tick_label_row.addWidget(self._tick_label_size_edit)
        tick_label_row.addStretch()
        layout.addLayout(tick_label_row)

        tick_metric_row = QHBoxLayout()
        tick_metric_row.addWidget(self._make_style_form_label("长度:", page))
        self._tick_length_edit = LineEdit(page)
        self._tick_length_edit.setPlaceholderText("默认")
        self._connect_line_edit_commit(self._tick_length_edit, self._on_quick_config_changed)
        self._set_compact_edit_width(self._tick_length_edit)
        tick_metric_row.addWidget(self._tick_length_edit)
        tick_metric_row.addWidget(self._make_style_form_label("宽度:", page))
        self._tick_width_edit = LineEdit(page)
        self._tick_width_edit.setPlaceholderText("默认")
        self._connect_line_edit_commit(self._tick_width_edit, self._on_quick_config_changed)
        self._set_compact_edit_width(self._tick_width_edit)
        tick_metric_row.addWidget(self._tick_width_edit)
        tick_metric_row.addStretch()
        layout.addLayout(tick_metric_row)

        layout.addWidget(make_hsep(page))
        layout.addWidget(make_section_label("图例与字体", page))

        legend_row = QHBoxLayout()
        legend_row.addWidget(self._make_style_form_label("图例位置:", page))
        self._legend_pos_combo = ComboBox(page)
        self._legend_pos_combo.addItems([
            "best", "upper right", "upper left", "lower left", "lower right",
            "right", "center left", "center right", "lower center", "upper center", "center",
        ])
        self._legend_pos_combo.currentIndexChanged.connect(self._on_quick_config_changed)
        legend_row.addWidget(self._legend_pos_combo, 1)
        layout.addLayout(legend_row)

        legend_anchor_row = QHBoxLayout()
        legend_anchor_row.addWidget(self._make_style_form_label("锚点 X:", page))
        self._legend_anchor_x_edit = LineEdit(page)
        self._legend_anchor_x_edit.setPlaceholderText("留空")
        self._legend_anchor_x_edit.setToolTip("与上方图例位置配合使用，按坐标轴比例设置 X 锚点，例如 0.02 或 1.0")
        self._legend_anchor_x_edit.textChanged.connect(self._on_legend_anchor_x_text_changed)
        self._legend_anchor_x_edit.editingFinished.connect(self._on_legend_anchor_x_committed)
        self._set_compact_edit_width(self._legend_anchor_x_edit)
        legend_anchor_row.addWidget(self._legend_anchor_x_edit)
        legend_anchor_row.addWidget(self._make_style_form_label("锚点 Y:", page))
        self._legend_anchor_y_edit = LineEdit(page)
        self._legend_anchor_y_edit.setPlaceholderText("留空")
        self._legend_anchor_y_edit.setToolTip("与上方图例位置配合使用，按坐标轴比例设置 Y 锚点，例如 0.98 或 0.5")
        self._legend_anchor_y_edit.textChanged.connect(self._on_legend_anchor_y_text_changed)
        self._legend_anchor_y_edit.editingFinished.connect(self._on_legend_anchor_y_committed)
        self._set_compact_edit_width(self._legend_anchor_y_edit)
        legend_anchor_row.addWidget(self._legend_anchor_y_edit)
        legend_anchor_row.addStretch()
        layout.addLayout(legend_anchor_row)

        font_row = QHBoxLayout()
        font_row.addWidget(self._make_style_form_label("字体族:", page))
        self._font_family_combo = ComboBox(page)
        self._font_family_combo.currentIndexChanged.connect(self._on_quick_config_changed)
        font_row.addWidget(self._font_family_combo, 1)
        layout.addLayout(font_row)

        font_size_row = QHBoxLayout()
        font_size_row.addWidget(self._make_style_form_label("字号:", page))
        self._font_size_edit = LineEdit(page)
        self._font_size_edit.setPlaceholderText("10")
        self._connect_line_edit_commit(self._font_size_edit, self._on_quick_config_changed)
        self._set_compact_edit_width(self._font_size_edit)
        font_size_row.addWidget(self._font_size_edit)
        
        font_size_row.addWidget(self._make_style_form_label("图例字号:", page))
        self._legend_font_size_edit = LineEdit(page)
        self._legend_font_size_edit.setPlaceholderText("8")
        self._connect_line_edit_commit(self._legend_font_size_edit, self._on_quick_config_changed)
        self._set_compact_edit_width(self._legend_font_size_edit)
        font_size_row.addWidget(self._legend_font_size_edit)
        font_size_row.addStretch()
        layout.addLayout(font_size_row)

        legend_frame_row = QHBoxLayout()
        self._legend_frame_cb = CheckBox("显示图例边框", page)
        self._legend_frame_cb.setChecked(True)
        self._legend_frame_cb.stateChanged.connect(self._on_quick_config_changed)
        legend_frame_row.addWidget(self._legend_frame_cb)
        legend_frame_row.addStretch()
        layout.addLayout(legend_frame_row)

        legend_frame_alpha_row = QHBoxLayout()
        legend_frame_alpha_row.addWidget(self._make_style_form_label("边框透明度:", page))
        self._legend_frame_alpha_slider = Slider(Qt.Orientation.Horizontal, page)
        self._legend_frame_alpha_slider.setRange(0, 100)
        self._legend_frame_alpha_slider.setSingleStep(1)
        self._legend_frame_alpha_slider.setPageStep(5)
        self._legend_frame_alpha_slider.setMinimumWidth(132)
        self._legend_frame_alpha_slider.setValue(self._alpha_slider_value(_LEGEND_ALPHA_DEFAULT))
        legend_frame_alpha_row.addWidget(self._legend_frame_alpha_slider, 1)
        self._legend_frame_alpha_value_label = BodyLabel("0.80", page)
        self._legend_frame_alpha_value_label.setStyleSheet(secondary_text_style_sheet(font_size=12))
        self._legend_frame_alpha_value_label.setMinimumWidth(40)
        legend_frame_alpha_row.addWidget(self._legend_frame_alpha_value_label)
        legend_frame_alpha_row.addStretch()
        self._update_alpha_value_label(self._legend_frame_alpha_value_label, self._legend_frame_alpha_slider.value())
        self._legend_frame_alpha_slider.valueChanged.connect(self._on_legend_frame_alpha_changed)
        layout.addLayout(legend_frame_alpha_row)

        legend_edge_color_row = QHBoxLayout()
        legend_edge_color_row.addWidget(self._make_style_form_label("边框颜色:", page))
        self._legend_edge_color_edit = LineEdit(page)
        self._legend_edge_color_edit.setPlaceholderText("留空跟随主题")
        self._connect_line_edit_commit(self._legend_edge_color_edit, self._on_quick_config_changed)
        legend_edge_color_row.addWidget(self._legend_edge_color_edit, 1)
        layout.addLayout(legend_edge_color_row)

        legend_face_color_row = QHBoxLayout()
        legend_face_color_row.addWidget(self._make_style_form_label("背景颜色:", page))
        self._legend_face_color_edit = LineEdit(page)
        self._legend_face_color_edit.setPlaceholderText("留空跟随画布")
        self._connect_line_edit_commit(self._legend_face_color_edit, self._on_quick_config_changed)
        legend_face_color_row.addWidget(self._legend_face_color_edit, 1)
        layout.addLayout(legend_face_color_row)

        legend_face_alpha_row = QHBoxLayout()
        legend_face_alpha_row.addWidget(self._make_style_form_label("背景透明度:", page))
        self._legend_face_alpha_slider = Slider(Qt.Orientation.Horizontal, page)
        self._legend_face_alpha_slider.setRange(0, 100)
        self._legend_face_alpha_slider.setSingleStep(1)
        self._legend_face_alpha_slider.setPageStep(5)
        self._legend_face_alpha_slider.setMinimumWidth(132)
        self._legend_face_alpha_slider.setValue(self._alpha_slider_value(_LEGEND_ALPHA_DEFAULT))
        legend_face_alpha_row.addWidget(self._legend_face_alpha_slider, 1)
        self._legend_face_alpha_value_label = BodyLabel("0.80", page)
        self._legend_face_alpha_value_label.setStyleSheet(secondary_text_style_sheet(font_size=12))
        self._legend_face_alpha_value_label.setMinimumWidth(40)
        legend_face_alpha_row.addWidget(self._legend_face_alpha_value_label)
        legend_face_alpha_row.addStretch()
        self._update_alpha_value_label(self._legend_face_alpha_value_label, self._legend_face_alpha_slider.value())
        self._legend_face_alpha_slider.valueChanged.connect(self._on_legend_face_alpha_changed)
        layout.addLayout(legend_face_alpha_row)

        layout.addWidget(make_hsep(page))
        layout.addWidget(make_section_label("画布与默认样式", page))

        canvas_color_row = QHBoxLayout()
        canvas_color_row.addWidget(self._make_style_form_label("画布颜色:", page))
        self._canvas_color_edit = LineEdit(page)
        self._canvas_color_edit.setPlaceholderText("留空跟随主题")
        self._connect_line_edit_commit(self._canvas_color_edit, self._on_quick_config_changed)
        canvas_color_row.addWidget(self._canvas_color_edit, 1)
        layout.addLayout(canvas_color_row)

        canvas_alpha_row = QHBoxLayout()
        canvas_alpha_row.addWidget(self._make_style_form_label("画布透明度:", page))
        self._canvas_alpha_slider = Slider(Qt.Orientation.Horizontal, page)
        self._canvas_alpha_slider.setRange(0, 100)
        self._canvas_alpha_slider.setSingleStep(1)
        self._canvas_alpha_slider.setPageStep(5)
        self._canvas_alpha_slider.setMinimumWidth(132)
        self._canvas_alpha_slider.setValue(self._alpha_slider_value(_CANVAS_ALPHA_DEFAULT))
        canvas_alpha_row.addWidget(self._canvas_alpha_slider, 1)
        self._canvas_alpha_value_label = BodyLabel("1.00", page)
        self._canvas_alpha_value_label.setStyleSheet(secondary_text_style_sheet(font_size=12))
        self._canvas_alpha_value_label.setMinimumWidth(40)
        canvas_alpha_row.addWidget(self._canvas_alpha_value_label)
        canvas_alpha_row.addStretch()
        self._update_alpha_value_label(self._canvas_alpha_value_label, self._canvas_alpha_slider.value())
        self._canvas_alpha_slider.valueChanged.connect(self._on_canvas_alpha_changed)
        layout.addLayout(canvas_alpha_row)

        figure_width_row = QHBoxLayout()
        figure_width_row.addWidget(self._make_style_form_label("图宽:", page))
        self._figure_width_edit = LineEdit(page)
        self._figure_width_edit.setPlaceholderText("7.0")
        self._connect_line_edit_commit(self._figure_width_edit, self._on_quick_config_changed)
        self._set_compact_edit_width(self._figure_width_edit)
        figure_width_row.addWidget(self._figure_width_edit)
        figure_width_row.addStretch()
        layout.addLayout(figure_width_row)

        figure_height_row = QHBoxLayout()
        figure_height_row.addWidget(self._make_style_form_label("图高:", page))
        self._figure_height_edit = LineEdit(page)
        self._figure_height_edit.setPlaceholderText("5.0")
        self._connect_line_edit_commit(self._figure_height_edit, self._on_quick_config_changed)
        self._set_compact_edit_width(self._figure_height_edit)
        figure_height_row.addWidget(self._figure_height_edit)
        figure_height_row.addStretch()
        layout.addLayout(figure_height_row)

        dpi_row = QHBoxLayout()
        dpi_row.addWidget(self._make_style_form_label("DPI:", page))
        self._dpi_edit = LineEdit(page)
        self._dpi_edit.setPlaceholderText("150")
        self._connect_line_edit_commit(self._dpi_edit, self._on_quick_config_changed)
        self._set_compact_edit_width(self._dpi_edit)
        dpi_row.addWidget(self._dpi_edit)
        dpi_row.addStretch()
        layout.addLayout(dpi_row)

        style_row = QHBoxLayout()
        style_row.addWidget(self._make_style_form_label("默认线宽:", page))
        self._plot_line_width_edit = LineEdit(page)
        self._plot_line_width_edit.setPlaceholderText("1.4")
        self._connect_line_edit_commit(self._plot_line_width_edit, self._on_quick_config_changed)
        self._set_compact_edit_width(self._plot_line_width_edit)
        style_row.addWidget(self._plot_line_width_edit)
        style_row.addStretch()
        layout.addLayout(style_row)

        marker_row = QHBoxLayout()
        marker_row.addWidget(self._make_style_form_label("默认点大小:", page))
        self._plot_marker_size_edit = LineEdit(page)
        self._plot_marker_size_edit.setPlaceholderText("5.0")
        self._connect_line_edit_commit(self._plot_marker_size_edit, self._on_quick_config_changed)
        self._set_compact_edit_width(self._plot_marker_size_edit)
        marker_row.addWidget(self._plot_marker_size_edit)
        marker_row.addStretch()
        layout.addLayout(marker_row)

        layout.addWidget(make_hsep(page))
        layout.addWidget(make_section_label("网格与边框", page))

        grid_toggle_row = QHBoxLayout()
        self._grid_cb = CheckBox("显示网格", page)
        self._grid_cb.stateChanged.connect(self._on_quick_config_changed)
        grid_toggle_row.addWidget(self._grid_cb)
        grid_toggle_row.addStretch()
        layout.addLayout(grid_toggle_row)

        grid_style_row = QHBoxLayout()
        grid_style_row.addWidget(self._make_style_form_label("网格透明度:", page))
        self._grid_alpha_slider = Slider(Qt.Orientation.Horizontal, page)
        self._grid_alpha_slider.setRange(0, 100)
        self._grid_alpha_slider.setSingleStep(1)
        self._grid_alpha_slider.setPageStep(5)
        self._grid_alpha_slider.setMinimumWidth(132)
        self._grid_alpha_slider.setValue(self._alpha_slider_value(_GRID_ALPHA_DEFAULT))
        grid_style_row.addWidget(self._grid_alpha_slider, 1)
        self._grid_alpha_value_label = BodyLabel("0.70", page)
        self._grid_alpha_value_label.setStyleSheet(secondary_text_style_sheet(font_size=12))
        self._grid_alpha_value_label.setMinimumWidth(40)
        grid_style_row.addWidget(self._grid_alpha_value_label)
        self._update_alpha_value_label(self._grid_alpha_value_label, self._grid_alpha_slider.value())
        self._grid_alpha_slider.valueChanged.connect(self._on_grid_alpha_changed)
        grid_style_row.addStretch()
        layout.addLayout(grid_style_row)

        grid_width_row = QHBoxLayout()
        grid_width_row.addWidget(self._make_style_form_label("网格线宽:", page))
        self._grid_line_width_edit = LineEdit(page)
        self._grid_line_width_edit.setPlaceholderText("0.5")
        self._connect_line_edit_commit(self._grid_line_width_edit, self._on_quick_config_changed)
        self._set_compact_edit_width(self._grid_line_width_edit)
        grid_width_row.addWidget(self._grid_line_width_edit)
        grid_width_row.addStretch()
        layout.addLayout(grid_width_row)

        spine_primary_toggle_row = QHBoxLayout()
        self._spine_bottom_cb = CheckBox("显示底部边框", page)
        self._spine_bottom_cb.setChecked(True)
        self._spine_bottom_cb.stateChanged.connect(self._on_quick_config_changed)
        spine_primary_toggle_row.addWidget(self._spine_bottom_cb)
        self._spine_left_cb = CheckBox("显示左侧边框", page)
        self._spine_left_cb.setChecked(True)
        self._spine_left_cb.stateChanged.connect(self._on_quick_config_changed)
        spine_primary_toggle_row.addWidget(self._spine_left_cb)
        spine_primary_toggle_row.addStretch()
        layout.addLayout(spine_primary_toggle_row)

        spine_secondary_toggle_row = QHBoxLayout()
        self._spine_top_cb = CheckBox("显示顶部边框", page)
        self._spine_top_cb.setChecked(True)
        self._spine_top_cb.stateChanged.connect(self._on_quick_config_changed)
        spine_secondary_toggle_row.addWidget(self._spine_top_cb)
        self._spine_right_cb = CheckBox("显示右侧边框", page)
        self._spine_right_cb.setChecked(True)
        self._spine_right_cb.stateChanged.connect(self._on_quick_config_changed)
        spine_secondary_toggle_row.addWidget(self._spine_right_cb)
        spine_secondary_toggle_row.addStretch()
        layout.addLayout(spine_secondary_toggle_row)

        spine_width_row = QHBoxLayout()
        spine_width_row.addWidget(self._make_style_form_label("边框线宽:", page))
        self._spine_width_edit = LineEdit(page)
        self._spine_width_edit.setPlaceholderText("默认")
        self._connect_line_edit_commit(self._spine_width_edit, self._on_quick_config_changed)
        self._set_compact_edit_width(self._spine_width_edit)
        spine_width_row.addWidget(self._spine_width_edit)
        spine_width_row.addStretch()
        layout.addLayout(spine_width_row)

        layout.addStretch()
        return scroll

    def _build_plot_extension_tab(self, parent: QWidget) -> QWidget:
        scroll, page, layout = self._create_style_tab_page(parent)
        page.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetDefaultConstraint)

        self._plot_extension_target_hint = make_hint_label("", page)
        self._plot_extension_target_hint.setWordWrap(True)
        self._plot_extension_target_hint.hide()

        self._plot_extension_controls = ExtensionConfigPanel("绘图扩展", "应用扩展", page, mode="compact", framed=False)
        self._plot_extension_controls.setMinimumWidth(0)
        self._plot_extension_controls.setMaximumWidth(16777215)
        self._plot_extension_controls.set_status_context("plot", "绘图扩展")
        self._plot_extension_controls.set_inline_apply_action(visible=True, tooltip="应用当前绘图扩展")
        self._plot_extension_controls.apply_requested.connect(self._on_chart_extension_apply)
        self._plot_extension_controls.configs_changed.connect(self.assets_modified.emit)
        self._plot_extension_controls.reload_requested.connect(self._reload_chart_extensions)
        self._plot_extension_controls.selection_changed.connect(self._on_plot_extension_type_changed)
        layout.addWidget(self._plot_extension_controls, 1)
        return scroll

    def on_tree_node_selected(self, kind: str, node_id: str) -> None:
        self._workspace_controller.handle_tree_selected(kind, node_id)

    def on_tree_node_activated(self, kind: str, node_id: str) -> None:
        if kind == "global_curve_style_template":
            self.load_curve_style_template(node_id)
            return
        if kind in ("global_plot_style", "global_plot_theme"):
            self.load_plot_style(node_id)
            return
        if kind.endswith("_to_chart"):
            kind = kind[:-9]
        if kind == "picture":
            self._load_picture_snapshot_from_node(node_id)
            return
        series_list = project_manager.get_all_series_from_node(kind, node_id)
        if not series_list:
            return
        self._add_series_batch(series_list, source="tree")

    def _build_picture_plot_snapshot(self) -> PicturePlotSnapshot:
        state = self._sync_state_from_controls().model_copy(deep=True)
        selected_curve = self._selected_curve()
        series_entries: List[PicturePlotSeriesSnapshot] = []
        for curve in self._chart_series:
            y_err = curve.get("y_err")
            series_entries.append(
                PicturePlotSeriesSnapshot(
                    curve_key=self._curve_key(curve),
                    curve_identity=self._curve_identity(curve),
                    name=str(curve.get("name") or ""),
                    display_name=self._curve_display_name(curve),
                    x=[float(value) for value in list(curve.get("x") or [])],
                    y=[float(value) for value in list(curve.get("y") or [])],
                    y_err=[float(value) for value in list(y_err)] if y_err is not None else None,
                    color=str(curve.get("color") or ""),
                    source=str(curve.get("source") or ""),
                    obj_id=str(curve.get("obj_id") or ""),
                    visible=bool(curve.get("visible", True)),
                )
            )

        applied_extensions: List[PicturePlotExtensionSnapshot] = []
        for applied in self._applied_plot_extensions:
            type_id = str(applied.get("type") or "")
            extension = extension_registry.get_plot(type_id)
            applied_extensions.append(
                PicturePlotExtensionSnapshot(
                    id=str(applied.get("id") or ""),
                    type=type_id,
                    sequence=int(applied.get("sequence") or 0),
                    options=copy.deepcopy(dict(applied.get("options") or {})),
                    curve_identity=str(applied.get("curve_identity") or "") or None,
                    curve_name=str(applied.get("curve_name") or ""),
                    curve_display_name=str(applied.get("curve_display_name") or ""),
                    extension_version=str(applied.get("extension_version") or getattr(extension, "version", "")),
                )
            )

        return PicturePlotSnapshot(
            style_change_sequence=int(self._style_change_sequence),
            figure_state=state,
            figure_state_change_versions={str(key): int(value) for key, value in self._figure_state_change_versions.items()},
            plot_style_extras=copy.deepcopy(self._plot_style_extras),
            plot_style_extra_versions=[
                PicturePlotExtraVersion(path=list(path), sequence=int(sequence))
                for path, sequence in self._plot_style_extra_versions.items()
            ],
            curve_styles={str(key): copy.deepcopy(dict(value)) for key, value in self._curve_styles.items()},
            curve_style_change_versions={
                str(identity): {str(key): int(sequence) for key, sequence in versions.items()}
                for identity, versions in self._curve_style_change_versions.items()
            },
            series=series_entries,
            applied_extensions=applied_extensions,
            selected_curve_key=(self._curve_key(selected_curve) if selected_curve is not None else self._style_target),
            applied_plot_style_ref=self._applied_plot_style_ref,
            active_template_id=self._active_template_node_id,
        )

    def _picture_snapshot_for_node(self, node_id: str) -> tuple[Optional[object], Optional[PicturePlotSnapshot]]:
        project = project_manager.current_project
        if project is None or project.tree is None:
            return None, None
        node = project.tree.get_node(node_id)
        if node is None or getattr(node, "kind", None) != "picture":
            return None, None
        picture_id = str(getattr(node, "picture_id", "") or "")
        if not picture_id:
            return None, None
        picture = project_manager.get_picture(picture_id)
        if picture is None:
            return None, None
        snapshot = picture.plot_snapshot.model_copy(deep=True) if picture.plot_snapshot is not None else None
        return picture, snapshot

    def _validate_picture_snapshot_extensions(self, snapshot: PicturePlotSnapshot) -> tuple[List[str], List[str]]:
        missing: List[str] = []
        mismatched: List[str] = []
        for applied in snapshot.applied_extensions:
            type_id = str(applied.type or "").strip()
            if not type_id:
                continue
            extension = extension_registry.get_plot(type_id)
            if extension is None:
                missing.append(type_id)
                continue
            saved_version = str(applied.extension_version or "").strip()
            current_version = str(getattr(extension, "version", "") or "").strip()
            if saved_version and current_version and compare_extension_versions(saved_version, current_version) != 0:
                mismatched.append(f"{extension.name} {saved_version} -> {current_version}")
        return missing, mismatched

    def _set_current_curve_item_by_key(self, curve_key: Optional[str]) -> None:
        target_key = str(curve_key or "").strip()
        if not target_key:
            return
        for index in range(self._chart_list.count()):
            item = self._chart_list.item(index)
            if str(item.data(Qt.ItemDataRole.UserRole) or "") == target_key:
                self._chart_list.setCurrentItem(item)
                return

    def _restore_picture_plot_snapshot(self, snapshot: PicturePlotSnapshot) -> None:
        restored_series: List[Dict[str, Any]] = []
        for index, entry in enumerate(snapshot.series, start=1):
            curve_key = str(entry.curve_key or entry.curve_identity or entry.obj_id or f"picture-curve-{index}")
            restored_series.append(
                {
                    "curve_key": curve_key,
                    "name": entry.name or f"曲线{index}",
                    "display_name": entry.display_name or entry.name or f"曲线{index}",
                    "x": [float(value) for value in entry.x],
                    "y": [float(value) for value in entry.y],
                    "y_err": [float(value) for value in entry.y_err] if entry.y_err is not None else None,
                    "color": entry.color,
                    "obj_id": entry.obj_id,
                    "source": entry.source,
                    "visible": bool(entry.visible),
                }
            )

        self._chart_series = restored_series
        self._curve_styles = {str(key): copy.deepcopy(dict(value)) for key, value in snapshot.curve_styles.items()}
        self._curve_style_change_versions = {
            str(identity): {str(key): int(sequence) for key, sequence in versions.items()}
            for identity, versions in snapshot.curve_style_change_versions.items()
        }
        self._figure_state_change_versions = {
            str(key): int(value) for key, value in snapshot.figure_state_change_versions.items()
        }
        self._plot_style_extras = copy.deepcopy(snapshot.plot_style_extras)
        self._plot_style_extra_versions = {
            tuple(str(part) for part in entry.path if str(part)): int(entry.sequence)
            for entry in snapshot.plot_style_extra_versions
            if entry.path
        }

        self._applied_plot_extensions = []
        self._plot_extension_options = {}
        self._plot_extension_instance_seed = 0
        max_sequence = int(snapshot.style_change_sequence)
        for index, applied in enumerate(snapshot.applied_extensions, start=1):
            instance_id = str(applied.id or f"plot-extension-{index}")
            self._applied_plot_extensions.append(
                {
                    "id": instance_id,
                    "type": str(applied.type or ""),
                    "sequence": int(applied.sequence),
                    "options": copy.deepcopy(dict(applied.options or {})),
                    "curve_identity": applied.curve_identity,
                    "curve_name": applied.curve_name,
                    "curve_display_name": applied.curve_display_name,
                    "extension_version": applied.extension_version,
                }
            )
            if applied.type:
                self._plot_extension_options[str(applied.type)] = copy.deepcopy(dict(applied.options or {}))
            try:
                if instance_id.startswith("plot-extension-"):
                    self._plot_extension_instance_seed = max(
                        self._plot_extension_instance_seed,
                        int(instance_id.rsplit("-", 1)[1]),
                    )
            except Exception:
                self._plot_extension_instance_seed = max(self._plot_extension_instance_seed, index)
            max_sequence = max(max_sequence, int(applied.sequence))

        self._style_change_sequence = max_sequence
        self._style_target = None
        self._active_template_node_id = snapshot.active_template_id
        self._applied_plot_style_ref = snapshot.applied_plot_style_ref
        self._active_curve_style_ref = None
        self._active_curve_style_template_id = None
        self._apply_figure_state(snapshot.figure_state.model_copy(deep=True))
        self._refresh_curve_style_template_combo()
        self._refresh_chart_list()
        self._set_current_curve_item_by_key(snapshot.selected_curve_key)
        self._refresh_plot_extension_list()
        self._refresh_style_extension_panel()
        self._redraw_now()

    def _load_picture_snapshot_from_node(self, node_id: str) -> bool:
        picture, snapshot = self._picture_snapshot_for_node(node_id)
        if picture is None:
            return False
        if snapshot is None:
            InfoBar.warning("提示", "当前图片未保存绘图信息", parent=self, position=InfoBarPosition.TOP)
            return False

        missing_extensions, mismatched_versions = self._validate_picture_snapshot_extensions(snapshot)
        if missing_extensions:
            InfoBar.error(
                "发送失败",
                "绘图中使用的扩展不存在或未加载",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return False
        if mismatched_versions:
            InfoBar.warning(
                "扩展版本不一致",
                "；".join(mismatched_versions),
                parent=self,
                position=InfoBarPosition.TOP,
            )
        if not MessageBox("确认覆盖当前绘图", "是否确认覆盖当前绘图？", self).exec():
            return False

        self._restore_picture_plot_snapshot(snapshot)
        InfoBar.success(
            "已发送到可视化",
            str(getattr(picture, "name", "") or "已恢复图片绘图"),
            parent=self,
            position=InfoBarPosition.TOP,
        )
        return True

    def _add_series_batch(self, series_list: List, source: str) -> None:
        added = False
        for series in series_list:
            added = self.add_series_to_chart({
                "name": series.name,
                "x": list(series.x),
                "y": list(series.y),
                "y_err": list(series.y_err) if getattr(series, "y_err", None) else None,
                "color": series.color,
                "obj_id": series.id,
                "source": source,
                "visible": True,
            }, redraw=False) or added
        if added:
            self._refresh_chart_list()
            self._redraw_now()

    def add_series_to_chart(self, series_data: dict, redraw: bool = True) -> bool:
        obj_id = series_data.get("obj_id", "")
        if obj_id and any(item.get("obj_id") == obj_id for item in self._chart_series):
            return False
        payload = dict(series_data)
        payload.setdefault("curve_key", payload.get("obj_id") or str(uuid.uuid4()))
        payload.setdefault("visible", True)
        payload.setdefault("display_name", payload.get("name", ""))
        self._chart_series.append(payload)
        if redraw:
            self._refresh_chart_list()
            self._redraw_now()
        return True

    @staticmethod
    def _curve_display_name(curve: dict) -> str:
        return (curve.get("display_name") or curve.get("name") or "未命名曲线").strip() or "未命名曲线"

    @staticmethod
    def _curve_key(curve: dict) -> str:
        return str(curve.get("curve_key") or curve.get("obj_id") or "")

    @staticmethod
    def _curve_identity(curve: dict) -> str:
        return ChartPage._curve_key(curve) or curve.get("name", "")

    def _next_style_change_sequence(self) -> int:
        self._style_change_sequence += 1
        return self._style_change_sequence

    def _record_figure_state_changes(self, keys: set[str] | List[str], *, sequence: Optional[int] = None) -> None:
        if not keys:
            return
        change_sequence = self._next_style_change_sequence() if sequence is None else sequence
        for key in keys:
            self._figure_state_change_versions[str(key)] = change_sequence

    def _record_plot_style_extra_changes(
        self,
        paths: set[tuple[str, ...]] | List[tuple[str, ...]],
        *,
        sequence: Optional[int] = None,
    ) -> None:
        if not paths:
            return
        change_sequence = self._next_style_change_sequence() if sequence is None else sequence
        for path in paths:
            clean_path = tuple(str(item) for item in path if str(item))
            if clean_path:
                self._plot_style_extra_versions[clean_path] = change_sequence

    def _record_curve_style_changes(
        self,
        curve_key: str,
        keys: set[str] | List[str],
        *,
        sequence: Optional[int] = None,
    ) -> None:
        clean_curve_key = str(curve_key or "").strip()
        if not clean_curve_key or not keys:
            return
        change_sequence = self._next_style_change_sequence() if sequence is None else sequence
        target_versions = self._curve_style_change_versions.setdefault(clean_curve_key, {})
        for key in keys:
            target_versions[str(key)] = change_sequence

    def _manual_plot_style_version(self, path: tuple[str, ...]) -> int:
        version = 0
        current_path = tuple(path)
        while current_path:
            version = max(version, self._plot_style_extra_versions.get(current_path, 0))
            current_path = current_path[:-1]
        return version

    def _plot_context_series_entry(
        self,
        curve: Optional[dict],
        *,
        style_payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if curve is None:
            return None
        entry = dict(curve)
        entry["curve_identity"] = self._curve_identity(curve)
        entry["display_name"] = self._curve_display_name(curve)
        entry["style"] = copy.deepcopy(style_payload if style_payload is not None else self._current_curve_style_payload(curve))
        return entry

    def _plot_context_series_entries(
        self,
        curves: List[dict],
        style_payloads: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for curve in curves:
            entry = self._plot_context_series_entry(
                curve,
                style_payload=style_payloads.get(self._curve_identity(curve), {}),
            )
            if entry is not None:
                entries.append(entry)
        return entries

    @staticmethod
    def _patch_can_override(layer: Dict[str, Any], field_sequence: int) -> bool:
        """判断扩展 layer 是否有权覆盖指定字段。

        - advisory（默认）：仅当扩展 sequence 大于 manual version 时覆盖
        - authoritative：总是覆盖
        """
        authority = str(layer.get("authority") or "advisory")
        if authority == "authoritative":
            return True
        sequence = int(layer.get("sequence") or 0)
        return sequence > field_sequence

    def _effective_plot_figure_state_payload(
        self,
        base_payload: Dict[str, Any],
        extension_layers: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        merged = dict(base_payload)
        for layer in extension_layers:
            for key, value in dict(layer.get("figure_state") or {}).items():
                clean_key = str(key)
                if self._patch_can_override(layer, self._figure_state_change_versions.get(clean_key, 0)):
                    merged[clean_key] = copy.deepcopy(value)
        return merged

    def _effective_plot_style_extras(
        self,
        base_extras: Dict[str, Any],
        extension_layers: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        merged = copy.deepcopy(base_extras)
        for layer in extension_layers:
            flattened = _flatten_nested_mapping(dict(layer.get("plot_style_extras") or {}))
            for path, value in flattened.items():
                if self._patch_can_override(layer, self._manual_plot_style_version(path)):
                    _set_nested_mapping_value(merged, path, value)
        return merged

    def _effective_curve_style_payloads(
        self,
        base_payloads: Dict[str, Dict[str, Any]],
        extension_layers: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        merged = {identity: copy.deepcopy(payload) for identity, payload in base_payloads.items()}
        for layer in extension_layers:
            for curve_identity, patch in dict(layer.get("curve_styles") or {}).items():
                clean_identity = str(curve_identity or "").strip()
                if not clean_identity:
                    continue
                target_payload = merged.setdefault(clean_identity, {})
                target_versions = self._curve_style_change_versions.get(clean_identity, {})
                for key, value in dict(patch or {}).items():
                    clean_key = str(key)
                    if self._patch_can_override(layer, target_versions.get(clean_key, 0)):
                        target_payload[clean_key] = copy.deepcopy(value)
        return merged

    def _curve_tree_path_label(self, curve: Optional[dict]) -> str:
        if curve is None:
            return "—"
        obj_id = str(curve.get("obj_id") or "")
        if obj_id:
            path = project_manager.format_series_origin_path_label(obj_id, separator="/", omit_root_group=True)
            if path:
                return path
        return "未关联项目树"

    def _curve_list_label(self, curve: Optional[dict]) -> str:
        if curve is None:
            return "未命名曲线"
        path_label = self._curve_tree_path_label(curve)
        if path_label not in {"—", "未关联项目树"}:
            return path_label
        return self._curve_display_name(curve)

    def _update_selected_curve_path_label(self, curve: Optional[dict]) -> None:
        path = self._curve_tree_path_label(curve)
        self._chart_path_label.setText(f"路径：{path}")
        self._chart_path_label.setToolTip(path if path not in {"—", "未关联项目树"} else "")
        install_fluent_tooltip(self._chart_path_label, delay=300, position=ToolTipPosition.BOTTOM)

    def _chart_list_tooltip_global_pos(self, event) -> QPoint:
        if hasattr(event, "globalPos"):
            return event.globalPos()
        if hasattr(event, "position"):
            return self._chart_list.viewport().mapToGlobal(event.position().toPoint())
        if hasattr(event, "pos"):
            return self._chart_list.viewport().mapToGlobal(event.pos())
        return self._chart_list.viewport().mapToGlobal(self._chart_list.viewport().rect().center())

    def _show_chart_list_tooltip(self, text: str, event) -> None:
        if not text:
            self._hide_chart_list_tooltip()
            return
        parent = self.window() if isinstance(self.window(), QWidget) else self
        self._view_state.chart_list_tooltip_visible = True
        if self._chart_list_tooltip is None:
            self._chart_list_tooltip = ToolTip(text, parent)
        self._chart_list_tooltip.setText(text)
        self._chart_list_tooltip.adjustSize()
        self._chart_list_tooltip.move(self._chart_list_tooltip_global_pos(event) + QPoint(12, 18))
        self._chart_list_tooltip.show()

    def _hide_chart_list_tooltip(self) -> None:
        self._view_state.chart_list_tooltip_visible = False
        if self._chart_list_tooltip is not None:
            self._chart_list_tooltip.hide()

    @staticmethod
    def _unique_style_label(base_label: str, used_labels: set[str], duplicate_suffix: str) -> str:
        label = base_label.strip() or "未命名样式"
        if label not in used_labels:
            used_labels.add(label)
            return label
        candidate = f"{label}（{duplicate_suffix}）"
        counter = 2
        while candidate in used_labels:
            candidate = f"{label}（{duplicate_suffix}{counter}）"
            counter += 1
        used_labels.add(candidate)
        return candidate

    def _plot_style_choices(self) -> List[tuple[str, str]]:
        choices: List[tuple[str, str]] = []
        used_labels: set[str] = set()
        for theme in global_assets.list_plot_themes(include_builtin=True):
            label = self._unique_style_label(theme.name or theme.id[:8], used_labels, "内置")
            choices.append((label, make_plot_style_asset_key("theme", theme.id or theme.name)))
        for figure in global_assets.list_figure_templates():
            label = self._unique_style_label(figure.name or figure.id[:8], used_labels, "已保存")
            choices.append((label, make_plot_style_asset_key("template", figure.id)))
        return choices

    def _plot_extension_entries(self) -> List[dict]:
        entries: List[dict] = []
        for extension in extension_registry.list_plot():
            entry = build_extension_entry(extension)
            if not entry.get("listed", True):
                continue
            entry["label"] = extension.name
            entries.append(entry)
        return entries

    def _next_plot_extension_instance_id(self) -> str:
        self._plot_extension_instance_seed += 1
        return f"plot-extension-{self._plot_extension_instance_seed}"

    def _resolve_plot_extension_curve(self, curve_identity: Optional[str], *, visible_only: bool = True) -> Optional[dict]:
        if not curve_identity:
            return None
        series = self._chart_series if not visible_only else [curve for curve in self._chart_series if curve.get("visible", True)]
        return next((curve for curve in series if self._curve_identity(curve) == curve_identity), None)

    @staticmethod
    def _plot_extension_option_summary(options: Dict[str, Any]) -> str:
        if not options:
            return "默认配置"
        parts: List[str] = []
        for index, (key, value) in enumerate(options.items()):
            if index >= 2:
                break
            rendered = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            rendered = str(rendered)
            if len(rendered) > 24:
                rendered = f"{rendered[:21]}..."
            parts.append(f"{key}={rendered}")
        if len(options) > 2:
            parts.append("...")
        return "，".join(parts)

    def _plot_extension_target_hint_text(self) -> str:
        selected_curve = self._selected_curve()
        if selected_curve is not None:
            return (
                f"当前选中：{self._curve_display_name(selected_curve)}\n"
                "应用扩展时，会把这条曲线记录为本次加载实例的目标曲线。"
            )

        visible_series = [curve for curve in self._chart_series if curve.get("visible", True)]
        if len(visible_series) > 1:
            return "当前选中：未选中\n当前画布存在多条曲线，建议先在“已绘图曲线”中选中目标曲线，再应用绘图扩展。"
        if len(visible_series) == 1:
            return (
                f"当前选中：未选中\n当前只有 {self._curve_display_name(visible_series[0])} 可见，"
                "扩展会按默认逻辑处理这条曲线。"
            )
        return "当前选中：未选中\n请先向画布添加曲线，再应用绘图扩展。"

    def _build_applied_plot_extension(self, type_id: str, options: Dict[str, Any]) -> Dict[str, Any]:
        target_curve = self._selected_curve()
        extension = extension_registry.get_plot(type_id)
        return {
            "id": self._next_plot_extension_instance_id(),
            "type": type_id,
            "sequence": self._next_style_change_sequence(),
            "options": dict(options),
            "curve_identity": self._curve_identity(target_curve) if target_curve is not None else None,
            "curve_name": target_curve.get("name") if target_curve is not None else None,
            "curve_display_name": self._curve_display_name(target_curve) if target_curve is not None else "",
            "extension_version": str(getattr(extension, "version", "")),
        }

    def _applied_plot_extension_label(self, entry: Dict[str, Any], index: int) -> str:
        extension = extension_registry.get_plot(str(entry.get("type") or ""))
        extension_name = extension.name if extension is not None else str(entry.get("type") or "绘图扩展")
        curve_identity = entry.get("curve_identity")
        selected_curve = self._selected_curve()
        selected_identity = self._curve_identity(selected_curve) if selected_curve is not None else None
        if curve_identity:
            curve = self._resolve_plot_extension_curve(str(curve_identity), visible_only=False)
            curve_label = (
                self._curve_display_name(curve)
                if curve is not None
                else f"{entry.get('curve_display_name') or entry.get('curve_name') or '目标曲线'}（已失效）"
            )
        else:
            curve_label = "全部可见曲线"
        current_hint = " · 当前选中" if selected_identity and selected_identity == curve_identity else ""
        summary = self._plot_extension_option_summary(dict(entry.get("options") or {}))
        return f"{index + 1}. {extension_name} · {curve_label} · {summary}{current_hint}"

    def _selected_plot_extension_instance(self) -> Optional[Dict[str, Any]]:
        if not hasattr(self, "_plot_extension_applied_list"):
            return None
        item = self._plot_extension_applied_list.currentItem()
        if item is None:
            return None
        instance_id = item.data(Qt.ItemDataRole.UserRole)
        return next((entry for entry in self._applied_plot_extensions if entry.get("id") == instance_id), None)

    def _refresh_plot_extension_list(self, *, selected_instance_id: Optional[str] = None) -> None:
        if hasattr(self, "_plot_extension_target_hint"):
            self._plot_extension_target_hint.setText(self._plot_extension_target_hint_text())
        if not hasattr(self, "_plot_extension_applied_list"):
            return

        current_item = self._plot_extension_applied_list.currentItem()
        target_instance_id = selected_instance_id
        if target_instance_id is None and current_item is not None:
            target_instance_id = current_item.data(Qt.ItemDataRole.UserRole)

        self._plot_extension_applied_list.blockSignals(True)
        self._plot_extension_applied_list.clear()
        target_row = -1
        for index, entry in enumerate(self._applied_plot_extensions):
            item = QListWidgetItem(self._applied_plot_extension_label(entry, index))
            item.setData(Qt.ItemDataRole.UserRole, entry.get("id"))
            tooltip_parts = []
            options = dict(entry.get("options") or {})
            if options:
                tooltip_parts.append("参数:")
                for key, value in options.items():
                    tooltip_parts.append(f"  {key}: {value}")
            impact_fields = []
            if entry.get("figure_state"):
                impact_fields.append("绘图状态")
            if entry.get("plot_style_extras"):
                impact_fields.append("绘图样式")
            if entry.get("curve_styles"):
                impact_fields.append("曲线样式")
            if impact_fields:
                tooltip_parts.append(f"影响范围: {', '.join(impact_fields)}")
            authority = entry.get("authority", "advisory")
            if authority != "advisory":
                tooltip_parts.append("接管模式: 强制覆盖")
            item.setToolTip("\n".join(tooltip_parts) if tooltip_parts else "无参数")
            self._plot_extension_applied_list.addItem(item)
            if entry.get("id") == target_instance_id:
                target_row = index
        if self._plot_extension_applied_list.count() > 0:
            if target_row < 0:
                target_row = 0
            self._plot_extension_applied_list.setCurrentRow(target_row)
        self._plot_extension_applied_list.blockSignals(False)
        self._sync_plot_extension_list_height()
        self._on_plot_extension_instance_selection_changed(self._plot_extension_applied_list.currentItem(), None)

    def _on_plot_extension_instance_selection_changed(self, current, _previous) -> None:
        has_selection = current is not None
        has_loaded = bool(self._applied_plot_extensions)
        if hasattr(self, "_clear_all_plot_extensions_btn"):
            self._clear_all_plot_extensions_btn.setEnabled(has_loaded)
        if hasattr(self, "_remove_selected_plot_extension_btn"):
            self._remove_selected_plot_extension_btn.setEnabled(has_selection)
        if not has_selection or not hasattr(self, "_plot_extension_controls"):
            current_type = self._plot_extension_controls.current_type() if hasattr(self, "_plot_extension_controls") else None
            self._update_plot_extension_info_panel(current_type)
            return
        applied = self._selected_plot_extension_instance()
        if applied is None:
            return
        type_id = str(applied.get("type") or "")
        target_index = next(
            (index for index, entry in enumerate(self._plot_extension_controls._entries) if entry.get("type") == type_id),
            -1,
        )
        if target_index >= 0:
            self._plot_extension_controls._selector.setCurrentIndex(target_index)
        self._plot_extension_controls._editor.setPlainText(json.dumps(dict(applied.get("options") or {}), ensure_ascii=False, indent=2))
        self._update_plot_extension_info_panel(type_id)

    def _remove_plot_extension_instance(self, instance_id: str) -> bool:
        if not instance_id:
            return False
        target = next((entry for entry in self._applied_plot_extensions if entry.get("id") == instance_id), None)
        if target is None:
            return False
        self._applied_plot_extensions = [entry for entry in self._applied_plot_extensions if entry.get("id") != instance_id]
        self._refresh_style_extension_panel()
        self._redraw_now()
        extension = extension_registry.get_plot(str(target.get("type") or ""))
        InfoBar.success(
            "已撤销",
            f"绘图扩展 {(extension.name if extension is not None else target.get('type') or '扩展')} 已移除",
            parent=self,
            position=InfoBarPosition.TOP,
        )
        return True

    def _remove_selected_plot_extension(self) -> None:
        applied = self._selected_plot_extension_instance()
        if applied is None:
            return
        self._remove_plot_extension_instance(str(applied.get("id") or ""))

    def _clear_all_plot_extensions(self) -> None:
        if not self._applied_plot_extensions:
            return
        dialog = MessageBox("确认清除全部扩展", "这会移除当前图表中已加载的全部绘图扩展，是否继续？", self)
        if not dialog.exec():
            return
        removed_count = len(self._applied_plot_extensions)
        self._applied_plot_extensions = []
        self._refresh_style_extension_panel()
        self._redraw_now()
        InfoBar.success(
            "已清除",
            f"已移除 {removed_count} 个绘图扩展",
            parent=self,
            position=InfoBarPosition.TOP,
        )

    def _extension_panel_context_target(self) -> str:
        current_tab = self._style_tabs.currentIndex()
        if current_tab == 0:
            selected_curve = self._selected_curve()
            return self._curve_display_name(selected_curve) if selected_curve is not None else "未选中曲线"
        return self._figure_state.theme or "绘图样式"

    def _sync_plot_extension_list_height(self) -> None:
        if not hasattr(self, "_plot_extension_applied_list"):
            return
        count = self._plot_extension_applied_list.count()
        row_height = self._plot_extension_applied_list.sizeHintForRow(0) if count > 0 else 32
        row_height = max(row_height, 32)
        frame_height = self._plot_extension_applied_list.frameWidth() * 2 + 6
        target_min_height = row_height * min(max(count, 1), 3) + frame_height
        self._plot_extension_applied_list.setMinimumHeight(max(target_min_height, 120))
        self._plot_extension_applied_list.setMaximumHeight(16777215)

    def _refresh_style_extension_panel(self, _index: Optional[int] = None) -> None:
        plot_entries = self._plot_extension_entries()
        available_types = {entry["type"] for entry in plot_entries}
        panel_current_type = self._plot_extension_controls.current_type() if hasattr(self, "_plot_extension_controls") else None
        current_type = None
        if panel_current_type in available_types:
            current_type = panel_current_type
        else:
            current_type = next(
                (str(entry.get("type")) for entry in reversed(self._applied_plot_extensions) if entry.get("type") in available_types),
                None,
            ) or next((type_id for type_id in self._plot_extension_options if type_id in available_types), None)
        if hasattr(self, "_plot_extension_controls"):
            self._plot_extension_controls.set_panel_title("绘图扩展")
            self._plot_extension_controls.set_action_text("应用扩展")
            self._plot_extension_controls.set_entries(
                plot_entries,
                saved_options=self._plot_extension_options,
                current_type=current_type,
            )
        self._update_plot_extension_info_panel(current_type)
        self._update_extension_remove_action()
        self._refresh_plot_extension_list()

    def _on_chart_extension_apply(self, type_id: str, options: Dict[str, Any]) -> None:
        self._plot_extension_options[type_id] = dict(options)
        self._apply_plot_extension(type_id)

    def _reload_chart_extensions(self) -> None:
        report = reload_configured_extensions()
        plot_types = {extension.type for extension in extension_registry.list_plot()}
        self._plot_extension_options = {key: value for key, value in self._plot_extension_options.items() if key in plot_types}
        self._applied_plot_extensions = [entry for entry in self._applied_plot_extensions if entry.get("type") in plot_types]
        self._refresh_curve_style_template_combo()
        self._refresh_template_combo(self._applied_plot_style_ref)
        self._refresh_style_extension_panel()
        self.extensions_reloaded.emit()
        if report.get("errors"):
            InfoBar.warning(
                "重载完成",
                f"已加载 {len(report.get('loaded', []))} 个扩展，{len(report.get('errors', []))} 个失败",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return
        InfoBar.success(
            "已重载",
            f"已重新加载 {len(report.get('loaded', []))} 个扩展",
            parent=self,
            position=InfoBarPosition.TOP,
        )

    def _available_font_family_choices(self) -> List[str]:
        matplotlib_fonts = list_matplotlib_font_families()
        qt_fonts: List[str] = []
        try:
            qt_fonts = [name.strip() for name in QFontDatabase.families() if name.strip()]
        except Exception:
            qt_fonts = []
        if qt_fonts:
            qt_set = set(qt_fonts)
            matched = [name for name in matplotlib_fonts if name in qt_set]
            if matched:
                return matched
        return matplotlib_fonts or sorted(set(qt_fonts), key=str.casefold)

    def _refresh_font_family_combo(self, current_font: str = "") -> None:
        choices = self._available_font_family_choices()
        clean_font = current_font.strip()
        if clean_font and clean_font not in choices:
            choices = [clean_font, *choices]

        self._font_family_combo.blockSignals(True)
        self._font_family_combo.clear()
        self._font_family_combo.addItem("默认")
        for name in choices:
            self._font_family_combo.addItem(name)
        if clean_font:
            idx = self._font_family_combo.findText(clean_font)
            self._font_family_combo.setCurrentIndex(idx if idx >= 0 else 0)
        else:
            self._font_family_combo.setCurrentIndex(0)
        self._font_family_combo.blockSignals(False)

    def receive_data(self, data_type: str, obj_id: str) -> None:
        series_list = project_manager.get_all_series_from_node(data_type, obj_id)
        self._add_series_batch(series_list, source="send")

    def _figure_template_choices(self) -> List[tuple[str, str]]:
        choices: List[tuple[str, str]] = []
        used_labels: set[str] = set()
        for figure in global_assets.list_figure_templates():
            label = figure.name or figure.id[:8]
            if label in used_labels:
                label = f"{label} ({figure.id[:8]})"
            used_labels.add(label)
            choices.append((label, figure.id))
        return choices

    def _refresh_template_combo(self, select_node_id: Optional[str] = None) -> None:
        choices = self._plot_style_choices()
        self._template_combo.blockSignals(True)
        self._template_combo.clear()
        self._template_combo.addItem("无")
        self._plot_style_refs = [None]
        for label, node_id in choices:
            self._template_combo.addItem(label)
            self._plot_style_refs.append(node_id)
        default_ref = self._applied_plot_style_ref
        if default_ref is None and self._active_template_node_id:
            default_ref = make_plot_style_asset_key("template", self._active_template_node_id)
        target_node_id = select_node_id if select_node_id is not None else default_ref
        if target_node_id in self._plot_style_refs:
            self._template_combo.setCurrentIndex(self._plot_style_refs.index(target_node_id))
        else:
            self._template_combo.setCurrentIndex(0)
        self._template_combo.blockSignals(False)
        self._update_template_summary()
        self._refresh_style_extension_panel()

    def _selected_template_node_id(self) -> Optional[str]:
        idx = self._template_combo.currentIndex()
        if idx < 0 or idx >= len(self._plot_style_refs):
            return None
        return self._plot_style_refs[idx]

    def _on_template_selected(self, idx: int) -> None:
        del idx
        self._update_template_summary()

    def _current_plot_style_ref(self) -> Optional[str]:
        return self._applied_plot_style_ref

    def _update_template_summary(self) -> None:
        current_ref = self._current_plot_style_ref()
        selected_ref = self._selected_template_node_id()
        pending_message = ""
        if selected_ref and selected_ref != current_ref:
            pending_message = f"已选择 {self._template_combo.currentText()}，点击加载后应用。\n"
        elif selected_ref is None and current_ref is not None and self._template_combo.currentIndex() == 0:
            pending_message = "已选择当前配置，点击加载后将解除样式绑定。\n"

        if self._active_template_node_id is not None:
            template = global_assets.get_figure_template(self._active_template_node_id)
            if template is not None:
                self._btn_update_template.setEnabled(True)
                if self._applied_plot_style_ref and self._applied_plot_style_ref.startswith("theme:"):
                    theme = global_assets.get_plot_theme(parse_plot_style_asset_key(self._applied_plot_style_ref)[1])
                    if theme is not None:
                        self._template_summary_label.setText(
                            f"{pending_message}正在编辑已保存样式: {template.name} · 已套用内置样式 {theme.name}".strip()
                        )
                        return
                self._template_summary_label.setText(
                    f"{pending_message}当前样式: {template.name} · 基础样式 {self._figure_state.theme}".strip()
                )
                return
            self._active_template_node_id = None

        if self._applied_plot_style_ref is None:
            self._template_summary_label.setText(
                f"{pending_message}当前为临时绘图样式，基础样式 {self._figure_state.theme}。".strip()
            )
            self._btn_update_template.setEnabled(False)
            return

        style_type, asset_id = parse_plot_style_asset_key(self._applied_plot_style_ref)
        if style_type == "template":
            template = global_assets.get_figure_template(asset_id)
            if template is not None:
                self._template_summary_label.setText(
                    f"{pending_message}当前样式: {template.name} · 基础样式 {self._figure_state.theme}".strip()
                )
                self._btn_update_template.setEnabled(True)
                return
        elif style_type == "theme":
            theme = global_assets.get_plot_theme(asset_id)
            if theme is not None:
                self._template_summary_label.setText(
                    f"{pending_message}当前使用内置绘图样式: {theme.name}".strip()
                )
                self._btn_update_template.setEnabled(False)
                return

        self._applied_plot_style_ref = None
        self._template_summary_label.setText(
            f"{pending_message}当前为临时绘图样式，基础样式 {self._figure_state.theme}。".strip()
        )
        self._btn_update_template.setEnabled(False)

    def _load_selected_plot_style(self) -> None:
        node_id = self._selected_template_node_id()
        if node_id is None:
            self._active_template_node_id = None
            self._applied_plot_style_ref = None
            self._refresh_template_combo()
            return
        self.load_plot_style(node_id)

    def load_plot_style(self, style_key: str) -> None:
        style_type, asset_id = parse_plot_style_asset_key(style_key)
        if style_type == "template":
            self.load_template(asset_id)
            return
        theme = global_assets.get_plot_theme(asset_id)
        if theme is None:
            return
        active_template_node_id = self._active_template_node_id
        current_state = self._sync_state_from_controls().model_copy(deep=True)
        state = theme.state.model_copy(deep=True)
        state.theme = theme.name
        state.x_label = current_state.x_label
        state.y_label = current_state.y_label
        state.x_min = current_state.x_min
        state.x_max = current_state.x_max
        state.y_min = current_state.y_min
        state.y_max = current_state.y_max
        state.x_log = current_state.x_log
        state.y_log = current_state.y_log
        state.show_errbar = current_state.show_errbar
        self._active_template_node_id = active_template_node_id
        self._applied_plot_style_ref = make_plot_style_asset_key("theme", theme.id or theme.name)
        self._current_plot_theme_id = theme.id
        self._apply_plot_style_payload(state.model_dump(), source="manual")
        self._redraw_now()
        self._refresh_style_extension_panel()

    def _apply_plot_extension(self, type_id: str) -> None:
        extension = extension_registry.get_plot(type_id)
        if extension is None:
            return
        extension_entry = build_extension_entry(extension)
        options = dict(
            self._plot_extension_options.get(
                type_id,
                dict(extension_entry.get("resolved_options") or extension.default_options or {}),
            )
        )
        self._plot_extension_options[type_id] = dict(options)
        applied = self._build_applied_plot_extension(type_id, options)
        self._applied_plot_extensions.append(applied)
        self._refresh_style_extension_panel()
        self._refresh_plot_extension_list(selected_instance_id=str(applied.get("id") or ""))
        self._redraw_now()

    def load_plot_theme(self, theme_id: str) -> None:
        self.load_plot_style(theme_id)

    def _resolve_plot_theme(self):
        return global_assets.get_plot_theme(self._current_plot_theme_id or self._figure_state.theme)

    def _theme_palette_for_state(self, state: FigureState) -> tuple[str, str, str]:
        theme = global_assets.get_plot_theme(state.theme) or self._resolve_plot_theme()
        dark = isDarkTheme()
        if theme is None or theme.canvas_mode == "app":
            background = theme.background_color if theme and theme.background_color else preview_canvas_background_color(dark)
            foreground = theme.foreground_color if theme and theme.foreground_color else preview_canvas_foreground_color(dark)
            grid_color = theme.grid_color if theme and theme.grid_color else preview_canvas_grid_color(dark)
            return background, foreground, grid_color
        if theme.canvas_mode == "dark":
            return (
                theme.background_color or preview_canvas_background_color(True),
                theme.foreground_color or preview_canvas_foreground_color(True),
                theme.grid_color or preview_canvas_grid_color(True),
            )
        return (
            theme.background_color or preview_canvas_background_color(False),
            theme.foreground_color or preview_canvas_foreground_color(False),
            theme.grid_color or preview_canvas_grid_color(False),
        )

    def load_template(self, template_node_id: str) -> None:
        figure = global_assets.get_figure_template(template_node_id)
        if figure is None:
            return
        axis = figure.typed_axis_config
        state = FigureState(
            theme=figure.theme or "默认",
            x_label=axis.x_label or "X",
            y_label=axis.y_label or "Y",
            figure_width=figure.figure_size[0] if len(figure.figure_size) > 0 else 7.0,
            figure_height=figure.figure_size[1] if len(figure.figure_size) > 1 else 5.0,
            dpi=figure.dpi or 150,
            show_errbar=figure.show_errbar,
            x_min=axis.x_min,
            x_max=axis.x_max,
            y_min=axis.y_min,
            y_max=axis.y_max,
            x_log=axis.x_log,
            y_log=axis.y_log,
            grid=figure.grid,
            grid_alpha=_clamp_float(figure.grid_alpha, 0.0, 1.0),
            grid_line_width=figure.grid_line_width,
            legend_pos=figure.legend_position or "best",
            font_size=figure.font_size or 10,
            font_family=figure.font_family or "",
            legend_font_size=figure.legend_font_size or 8,
            line_width=figure.line_width or 1.4,
            marker_size=figure.marker_size or 5.0,
        )
        self._active_template_node_id = figure.id
        self._applied_plot_style_ref = make_plot_style_asset_key("template", figure.id)
        payload = state.model_dump()
        payload.update(copy.deepcopy(dict(figure.style_extras or {})))
        self._apply_plot_style_payload(payload, source="manual")
        self._refresh_style_extension_panel()
        self._redraw_now()

    def _build_figure_config(self, name: str, figure_id: Optional[str] = None) -> Optional[FigureConfig]:
        clean_name = name.strip()
        if not clean_name:
            return None
        state = self._sync_state_from_controls()
        axis = AxisConfig(
            x_label=state.x_label,
            y_label=state.y_label,
            x_min=state.x_min,
            x_max=state.x_max,
            y_min=state.y_min,
            y_max=state.y_max,
            x_log=state.x_log,
            y_log=state.y_log,
        )
        config = FigureConfig(
            name=clean_name,
            theme=state.theme,
            show_errbar=state.show_errbar,
            typed_axis_config=axis,
            figure_size=(state.figure_width, state.figure_height),
            dpi=state.dpi,
            grid=state.grid,
            grid_alpha=state.grid_alpha,
            grid_line_width=state.grid_line_width,
            legend_position=state.legend_pos,
            font_size=state.font_size,
            font_family=state.font_family,
            legend_font_size=state.legend_font_size,
            line_width=state.line_width,
            marker_size=state.marker_size,
            style_extras=copy.deepcopy(self._plot_style_extras),
        )
        if figure_id:
            config.id = figure_id
        return config

    def _save_template_named(self, name: str):
        config = self._build_figure_config(name)
        if config is None:
            return None
        template = project_manager.add_figure_template(config)
        if template is not None:
            self._active_template_node_id = template.id
            self._applied_plot_style_ref = make_plot_style_asset_key("template", template.id)
            self._refresh_template_combo(self._applied_plot_style_ref)
        return template

    def _on_save_template(self) -> None:
        name, ok = TextInputDialog.get_text(self, "保存绘图样式", "样式名称:", placeholder="输入样式名称")
        if not ok or not name.strip():
            return
        template = self._save_template_named(name)
        if template is not None:
            InfoBar.success("已保存", f"样式「{name.strip()}」已存入全局资源", parent=self, position=InfoBarPosition.TOP)
            self.project_modified.emit()
            self.assets_modified.emit()

    def _on_load_template(self) -> None:
        choices = self._plot_style_choices()
        if not choices:
            InfoBar.warning("提示", "当前没有可加载的绘图样式", parent=self, position=InfoBarPosition.TOP)
            return
        names = [label for label, _ in choices]
        selected, ok = SelectionDialog.get_item(self, "加载绘图样式", "样式名称:", names)
        if not ok or not selected:
            return
        selected_node_id = next((node_id for label, node_id in choices if label == selected), None)
        if selected_node_id:
            self._refresh_template_combo(selected_node_id)
            self._load_selected_plot_style()

    def _on_update_template(self) -> None:
        if self._update_current_template():
            InfoBar.success("已更新", "当前绘图样式已覆盖更新", parent=self, position=InfoBarPosition.TOP)

    def _update_current_template(self) -> bool:
        if self._active_template_node_id is None:
            InfoBar.warning("提示", "请先加载一个已保存绘图样式", parent=self, position=InfoBarPosition.TOP)
            return False
        template = global_assets.get_figure_template(self._active_template_node_id)
        if template is None:
            InfoBar.warning("提示", "当前绘图样式已不存在，请刷新样式列表", parent=self, position=InfoBarPosition.TOP)
            self._refresh_template_combo()
            return False
        config = self._build_figure_config(template.name, figure_id=template.id)
        if config is None:
            return False
        if not project_manager.save_figure_config(config):
            InfoBar.error("失败", "更新绘图样式失败", parent=self, position=InfoBarPosition.TOP)
            return False
        self._applied_plot_style_ref = make_plot_style_asset_key("template", template.id)
        self._refresh_template_combo(self._applied_plot_style_ref)
        self.project_modified.emit()
        self.assets_modified.emit()
        return True

    def _refresh_curve_style_template_combo(self) -> None:
        templates = global_assets.list_curve_style_templates()
        self._curve_style_template_combo.blockSignals(True)
        self._curve_style_template_combo.clear()
        self._curve_style_template_combo.addItem("无")
        self._curve_style_template_ids = [None]
        for item in templates:
            self._curve_style_template_combo.addItem(item.name)
            self._curve_style_template_ids.append(item.id)
        target_id = self._active_curve_style_ref
        if target_id in self._curve_style_template_ids:
            self._curve_style_template_combo.setCurrentIndex(self._curve_style_template_ids.index(target_id))
        else:
            self._curve_style_template_combo.setCurrentIndex(0)
        self._curve_style_template_combo.blockSignals(False)
        self._update_curve_style_template_summary()
        self._refresh_style_extension_panel()

    def handle_extension_runtime_reload(self, valid_plot_types: set[str]) -> None:
        self._plot_extension_options = {
            key: value for key, value in self._plot_extension_options.items() if key in valid_plot_types
        }
        self._applied_plot_extensions = [
            entry for entry in self._applied_plot_extensions if entry.get("type") in valid_plot_types
        ]
        self._refresh_curve_style_template_combo()
        self._refresh_template_combo(self._applied_plot_style_ref)
        self._refresh_style_extension_panel()

    def _update_curve_style_template_summary(self) -> None:
        if not self._active_curve_style_ref:
            self._curve_style_template_label.setText("当前曲线样式未绑定全局模板。")
            self._btn_update_curve_style_template.setEnabled(False)
            return
        template = global_assets.get_curve_style_template(self._active_curve_style_ref)
        if template is None:
            self._active_curve_style_template_id = None
            self._active_curve_style_ref = None
            self._active_curve_style_template_id = None
            self._curve_style_template_label.setText("当前曲线样式未绑定全局模板。")
            self._btn_update_curve_style_template.setEnabled(False)
            self._refresh_style_extension_panel()
            return
        self._curve_style_template_label.setText(f"当前全局模板: {template.name}")
        self._btn_update_curve_style_template.setEnabled(True)
        self._refresh_style_extension_panel()

    def _selected_curve_style_template_id(self) -> Optional[str]:
        idx = self._curve_style_template_combo.currentIndex()
        if idx < 0 or idx >= len(self._curve_style_template_ids):
            return None
        return self._curve_style_template_ids[idx]

    def _on_curve_style_template_selected(self, idx: int) -> None:
        if idx <= 0:
            self._active_curve_style_template_id = None
            self._active_curve_style_ref = None
            self._update_curve_style_template_summary()
            return
        style_ref = self._selected_curve_style_template_id()
        if style_ref:
            self._active_curve_style_ref = style_ref
            self._active_curve_style_template_id = style_ref
            self._update_curve_style_template_summary()

    def _load_selected_curve_style_template(self) -> None:
        style_ref = self._selected_curve_style_template_id()
        if not style_ref:
            InfoBar.warning("提示", "请先选择一个曲线样式", parent=self, position=InfoBarPosition.TOP)
            return
        self.load_curve_style_template(style_ref)

    def load_curve_style_template(self, template_id: str) -> None:
        template = global_assets.get_curve_style_template(template_id)
        if template is None:
            return
        curve = self._selected_curve()
        if curve is None:
            InfoBar.warning("提示", "请先选中一条曲线再应用样式模板", parent=self, position=InfoBarPosition.TOP)
            return
        self._apply_curve_style(self._curve_key(curve), template.style)
        self._active_curve_style_template_id = template.id
        self._active_curve_style_ref = template.id
        self._refresh_curve_style_template_combo()
        self._redraw_now()

    def _current_curve_style(self, curve: Optional[dict] = None) -> Optional[CurveStyle]:
        target_curve = curve or self._selected_curve()
        if target_curve is None:
            return None
        overrides = self._curve_styles.get(self._curve_key(target_curve), {})
        return CurveStyle(
            color=overrides.get("color") or target_curve.get("color"),
            linestyle=overrides.get("linestyle", "-"),
            marker=overrides.get("marker", ""),
            linewidth=_safe_float_or(overrides.get("linewidth"), self._figure_state.line_width),
            marker_size=_safe_float_or(overrides.get("marker_size"), self._figure_state.marker_size),
            alpha=_safe_float_or(overrides.get("alpha"), 1.0),
            markevery=max(1, _safe_int_or(overrides.get("markevery"), 1)),
            dash_scale=_safe_float_or(overrides.get("dash_scale"), 1.0),
            visible=bool(target_curve.get("visible", True)),
        )

    def _current_curve_style_payload(self, curve: Optional[dict] = None) -> Dict[str, Any]:
        target_curve = curve or self._selected_curve()
        style = self._current_curve_style(target_curve)
        if target_curve is None or style is None:
            return {}
        payload = style.model_dump()
        overrides = self._curve_styles.get(self._curve_key(target_curve), {})
        for key, value in overrides.items():
            if key not in payload:
                payload[key] = value
        return payload

    def _apply_curve_style(self, curve_key: str, style: CurveStyle) -> None:
        self._apply_curve_style_payload(curve_key, style.model_dump())

    def _apply_curve_style_payload(self, curve_key: str, payload: Dict[str, Any], *, source: str = "manual") -> None:
        style_dict = self._curve_styles.setdefault(curve_key, {})
        for key, value in payload.items():
            if key == "visible":
                continue
            if value is None:
                style_dict.pop(key, None)
                continue
            style_dict[key] = value
        if source == "manual":
            self._record_curve_style_changes(curve_key, {str(key) for key in payload.keys()})
        for curve in self._chart_series:
            if self._curve_key(curve) == curve_key:
                if "visible" in payload:
                    curve["visible"] = bool(payload.get("visible", True))
                break
        self._refresh_chart_list()
        selected_curve = self._selected_curve()
        if selected_curve and self._curve_key(selected_curve) == curve_key:
            self._set_style_enabled(True, selected_curve)

    def _base_style_plot_context(self, *, selected_curve: Optional[dict] = None) -> PlotExtensionContext:
        current_state = self._figure_state.model_dump()
        bg, fg, grid = self._theme_palette_for_state(self._figure_state)
        target_curve = selected_curve or self._selected_curve()
        visible_series = [curve for curve in self._chart_series if curve.get("visible", True)]
        visible_payloads = {
            self._curve_identity(curve): self._current_curve_style_payload(curve)
            for curve in visible_series
        }
        axes = list(self._figure.axes) if self._figure is not None else []
        axis = axes[0] if axes else None
        return PlotExtensionContext(
            figure=self._figure,
            canvas=self._canvas,
            axis=axis,
            axes=axes,
            visible_series=self._plot_context_series_entries(visible_series, visible_payloads),
            plotted_series=[],
            selected_series=(
                self._plot_context_series_entry(
                    target_curve,
                    style_payload=self._current_curve_style_payload(target_curve),
                )
                if target_curve is not None
                else None
            ),
            selected_series_identity=self._curve_identity(target_curve) if target_curve is not None else None,
            figure_state=copy.deepcopy(current_state),
            plot_style_extras=copy.deepcopy(self._plot_style_extras),
            theme_colors={"background": bg, "foreground": fg, "grid": grid},
            phase="before_plot",
        )

    def _apply_base_curve_style_options(self, options: Dict[str, Any]) -> None:
        target_curve = self._selected_curve()
        if target_curve is None:
            return
        extension = extension_registry.get_plot(_BASE_CURVE_STYLE_EXTENSION_TYPE)
        if extension is None:
            return
        plot_context = self._base_style_plot_context(selected_curve=target_curve)
        extension.handler(plot_context, dict(options or {}))
        patch = dict(plot_context.curve_style_patches.get(self._curve_identity(target_curve), {}) or {})
        if not patch:
            return
        self._apply_curve_style_payload(self._curve_key(target_curve), patch, source="manual")

    def _apply_base_plot_style_options(
        self,
        options: Dict[str, Any],
        *,
        changed_keys: Optional[set[str]] = None,
        extra_options: Optional[Dict[str, Any]] = None,
        changed_extra_paths: Optional[set[tuple[str, ...]]] = None,
    ) -> None:
        extension = extension_registry.get_plot(_BASE_PLOT_STYLE_EXTENSION_TYPE)
        if extension is None:
            return
        plot_context = self._base_style_plot_context(selected_curve=self._selected_curve())
        extension.handler(plot_context, dict(options or {}))
        payload = dict(plot_context.figure_state_patch or {})
        if extra_options is not None:
            payload = _merge_nested_mapping(payload, copy.deepcopy(extra_options))
            if changed_extra_paths:
                self._record_plot_style_extra_changes(changed_extra_paths)
        elif plot_context.plot_style_patch:
            payload = _merge_nested_mapping(payload, dict(plot_context.plot_style_patch or {}))
            changed_paths = set(_flatten_nested_mapping(dict(plot_context.plot_style_patch or {})).keys())
            if changed_paths:
                self._record_plot_style_extra_changes(changed_paths)
        if changed_keys:
            self._record_figure_state_changes(changed_keys)
        if not payload and extra_options is None:
            return
        preserve_partial_legend_anchor_draft = self._preserve_partial_legend_anchor_draft
        self._preserve_partial_legend_anchor_draft = extra_options is not None
        try:
            self._apply_plot_style_payload(payload, source="extension")
        finally:
            self._preserve_partial_legend_anchor_draft = preserve_partial_legend_anchor_draft

    def _save_curve_style_template_named(self, name: str) -> bool:
        style = self._current_curve_style()
        if style is None or not name.strip():
            return False
        template = global_assets.add_curve_style_template(CurveStyleTemplate(name=name.strip(), style=style))
        self._active_curve_style_template_id = template.id
        self._active_curve_style_ref = template.id
        self._refresh_curve_style_template_combo()
        self.assets_modified.emit()
        return True

    def _on_save_curve_style_template(self) -> None:
        if self._selected_curve() is None:
            InfoBar.warning("提示", "请先选中一条曲线", parent=self, position=InfoBarPosition.TOP)
            return
        name, ok = TextInputDialog.get_text(self, "保存曲线样式", "样式名称:", placeholder="输入样式名称")
        if ok and self._save_curve_style_template_named(name):
            InfoBar.success("已保存", f"曲线样式 {name.strip()} 已保存", parent=self, position=InfoBarPosition.TOP)

    def _on_update_curve_style_template(self) -> None:
        if not self._active_curve_style_template_id:
            InfoBar.warning("提示", "请先选择一个曲线样式", parent=self, position=InfoBarPosition.TOP)
            return
        if self._selected_curve() is None:
            InfoBar.warning("提示", "请先选中一条曲线", parent=self, position=InfoBarPosition.TOP)
            return
        style = self._current_curve_style()
        if style is None:
            return
        if global_assets.update_curve_style_template(self._active_curve_style_template_id, style=style):
            self.assets_modified.emit()
            InfoBar.success("已更新", "当前曲线样式已覆盖更新", parent=self, position=InfoBarPosition.TOP)

    def _get_current_config(self) -> dict:
        config = self._figure_state.model_dump()
        config.update(self._plot_style_extras)
        return config

    def _apply_advanced_config(self, cfg: dict) -> None:
        payload = _merge_nested_mapping(self._get_current_config(), cfg)
        self._applied_plot_style_ref = (
            make_plot_style_asset_key("template", self._active_template_node_id)
            if self._active_template_node_id
            else None
        )
        self._apply_plot_style_payload(payload, source="manual")
        self._redraw_now()

    def _current_plot_style_payload(self) -> Dict[str, Any]:
        payload = self._sync_state_from_controls().model_dump()
        payload.update(self._plot_style_extras)
        return payload

    def _apply_plot_style_payload(self, payload: Dict[str, Any], *, source: str = "manual") -> None:
        figure_fields = set(FigureState.model_fields.keys())
        previous_state_payload = self._figure_state.model_dump()
        state_payload = dict(previous_state_payload)
        state_payload.update({key: value for key, value in payload.items() if key in figure_fields})
        next_plot_style_extras = {key: copy.deepcopy(value) for key, value in payload.items() if key not in figure_fields}
        if source == "manual":
            changed_state_keys = {
                key for key in figure_fields
                if previous_state_payload.get(key) != state_payload.get(key)
            }
            changed_extra_paths = _nested_mapping_changed_paths(self._plot_style_extras, next_plot_style_extras)
            if changed_state_keys or changed_extra_paths:
                sequence = self._next_style_change_sequence()
                self._record_figure_state_changes(changed_state_keys, sequence=sequence)
                self._record_plot_style_extra_changes(changed_extra_paths, sequence=sequence)
        self._plot_style_extras = next_plot_style_extras
        self._apply_plot_style_extra_controls()
        self._apply_figure_state(FigureState(**state_payload), apply_extra_controls=False)

    def _plot_style_extra_options_from_controls(self) -> Dict[str, Any]:
        extras: Dict[str, Any] = {}

        tick_defaults = {
            "bottom": True,
            "left": True,
            "top": False,
            "right": False,
            "labelbottom": True,
            "labelleft": True,
            "labeltop": False,
            "labelright": False,
        }
        tick_params: Dict[str, Any] = {}
        tick_states = {
            "bottom": bool(self._tick_bottom_cb.isChecked()),
            "left": bool(self._tick_left_cb.isChecked()),
            "top": bool(self._tick_top_cb.isChecked()),
            "right": bool(self._tick_right_cb.isChecked()),
            "labelbottom": bool(self._tick_label_bottom_cb.isChecked()),
            "labelleft": bool(self._tick_label_left_cb.isChecked()),
            "labeltop": bool(self._tick_label_top_cb.isChecked()),
            "labelright": bool(self._tick_label_right_cb.isChecked()),
        }
        for key, value in tick_states.items():
            if value != tick_defaults[key]:
                tick_params[key] = value
        tick_direction = self._tick_direction_combo.currentText().strip()
        if tick_direction and tick_direction != "默认":
            tick_params["direction"] = tick_direction
        tick_label_size = _safe_int(self._tick_label_size_edit.text())
        if tick_label_size is not None and tick_label_size > 0:
            tick_params["labelsize"] = tick_label_size
        tick_length = _safe_float(self._tick_length_edit.text())
        if tick_length is not None and tick_length >= 0:
            tick_params["length"] = tick_length
        tick_width = _safe_float(self._tick_width_edit.text())
        if tick_width is not None and tick_width >= 0:
            tick_params["width"] = tick_width
        if tick_params:
            extras["tick_params"] = tick_params

        legend_kwargs: Dict[str, Any] = {}
        if not self._legend_frame_cb.isChecked():
            legend_kwargs["frameon"] = False
        legend_frame_alpha = self._alpha_from_slider_value(self._legend_frame_alpha_slider.value())
        if abs(legend_frame_alpha - _LEGEND_ALPHA_DEFAULT) > 1e-6:
            legend_kwargs["edgealpha"] = legend_frame_alpha
        legend_edge_color = _safe_color(self._legend_edge_color_edit.text())
        if legend_edge_color:
            legend_kwargs["edgecolor"] = legend_edge_color
        legend_face_color = _safe_color(self._legend_face_color_edit.text())
        if legend_face_color:
            legend_kwargs["facecolor"] = legend_face_color
        legend_face_alpha = self._alpha_from_slider_value(self._legend_face_alpha_slider.value())
        if abs(legend_face_alpha - _LEGEND_ALPHA_DEFAULT) > 1e-6:
            legend_kwargs["facealpha"] = legend_face_alpha
        legend_anchor_x = _safe_float(self._legend_anchor_x_edit.text().strip() or self._legend_anchor_x_draft)
        legend_anchor_y = _safe_float(self._legend_anchor_y_edit.text().strip() or self._legend_anchor_y_draft)
        if legend_anchor_x is not None and legend_anchor_y is not None:
            legend_kwargs["bbox_to_anchor"] = [legend_anchor_x, legend_anchor_y]
        if legend_kwargs:
            if self._legend_frame_cb.isChecked() and any(key in legend_kwargs for key in {"framealpha", "edgecolor", "facecolor"}):
                legend_kwargs.setdefault("frameon", True)
            extras["legend_kwargs"] = legend_kwargs

        spine_visibility: Dict[str, Any] = {}
        if not self._spine_bottom_cb.isChecked():
            spine_visibility["bottom"] = False
        if not self._spine_left_cb.isChecked():
            spine_visibility["left"] = False
        if not self._spine_top_cb.isChecked():
            spine_visibility["top"] = False
        if not self._spine_right_cb.isChecked():
            spine_visibility["right"] = False
        if spine_visibility:
            extras["spine_visibility"] = spine_visibility

        spine_width = _safe_float(self._spine_width_edit.text())
        if spine_width is not None and spine_width >= 0:
            extras["spine_width"] = spine_width

        canvas_color = _safe_color(self._canvas_color_edit.text())
        if canvas_color:
            extras["figure_facecolor"] = canvas_color
        canvas_alpha = self._alpha_from_slider_value(self._canvas_alpha_slider.value())
        if abs(canvas_alpha - _CANVAS_ALPHA_DEFAULT) > 1e-6:
            extras["figure_facealpha"] = canvas_alpha

        return extras

    def _apply_plot_style_extra_controls(self) -> None:
        tick_params = dict(self._plot_style_extras.get("tick_params") or {})
        legend_kwargs = dict(self._plot_style_extras.get("legend_kwargs") or {})
        spine_visibility = dict(self._plot_style_extras.get("spine_visibility") or {})

        for checkbox, checked in (
            (self._spine_bottom_cb, bool(spine_visibility.get("bottom", True))),
            (self._spine_left_cb, bool(spine_visibility.get("left", True))),
            (self._tick_bottom_cb, bool(tick_params.get("bottom", True))),
            (self._tick_left_cb, bool(tick_params.get("left", True))),
            (self._tick_top_cb, bool(tick_params.get("top", False))),
            (self._tick_right_cb, bool(tick_params.get("right", False))),
            (self._tick_label_bottom_cb, bool(tick_params.get("labelbottom", True))),
            (self._tick_label_left_cb, bool(tick_params.get("labelleft", True))),
            (self._tick_label_top_cb, bool(tick_params.get("labeltop", False))),
            (self._tick_label_right_cb, bool(tick_params.get("labelright", False))),
            (self._legend_frame_cb, bool(legend_kwargs.get("frameon", True))),
            (self._spine_top_cb, bool(spine_visibility.get("top", True))),
            (self._spine_right_cb, bool(spine_visibility.get("right", True))),
        ):
            checkbox.blockSignals(True)
            checkbox.setChecked(checked)
            checkbox.blockSignals(False)

        self._tick_direction_combo.blockSignals(True)
        direction = str(tick_params.get("direction") or "默认")
        direction_index = self._tick_direction_combo.findText(direction)
        self._tick_direction_combo.setCurrentIndex(direction_index if direction_index >= 0 else 0)
        self._tick_direction_combo.blockSignals(False)

        _set_line_edit_text(self._tick_label_size_edit, tick_params.get("labelsize"), allow_blank=True)
        _set_line_edit_text(self._tick_length_edit, tick_params.get("length"), allow_blank=True)
        _set_line_edit_text(self._tick_width_edit, tick_params.get("width"), allow_blank=True)
        legend_frame_alpha = _safe_float(legend_kwargs.get("edgealpha"))
        if legend_frame_alpha is None:
            legend_frame_alpha = _safe_float(legend_kwargs.get("framealpha"))
        self._set_alpha_slider_value(
            self._legend_frame_alpha_slider,
            self._legend_frame_alpha_value_label,
            legend_frame_alpha,
            default_alpha=_LEGEND_ALPHA_DEFAULT,
        )
        _set_line_edit_text(self._legend_edge_color_edit, legend_kwargs.get("edgecolor"), allow_blank=True)
        _set_line_edit_text(self._legend_face_color_edit, legend_kwargs.get("facecolor"), allow_blank=True)
        legend_face_alpha = _safe_float(legend_kwargs.get("facealpha"))
        if legend_face_alpha is None:
            legend_face_alpha = _safe_float(legend_kwargs.get("framealpha"))
        self._set_alpha_slider_value(
            self._legend_face_alpha_slider,
            self._legend_face_alpha_value_label,
            legend_face_alpha,
            default_alpha=_LEGEND_ALPHA_DEFAULT,
        )
        legend_anchor = legend_kwargs.get("bbox_to_anchor")
        if isinstance(legend_anchor, (list, tuple)) and len(legend_anchor) >= 2:
            _set_line_edit_text(self._legend_anchor_x_edit, legend_anchor[0], allow_blank=True)
            _set_line_edit_text(self._legend_anchor_y_edit, legend_anchor[1], allow_blank=True)
            self._legend_anchor_x_draft = self._legend_anchor_x_edit.text().strip()
            self._legend_anchor_y_draft = self._legend_anchor_y_edit.text().strip()
        else:
            preserve_partial_anchor = bool(
                self._preserve_partial_legend_anchor_draft
                and (self._legend_anchor_x_edit.text().strip() or self._legend_anchor_y_edit.text().strip())
            )
            _set_line_edit_text(self._legend_anchor_x_edit, None, allow_blank=True)
            _set_line_edit_text(self._legend_anchor_y_edit, None, allow_blank=True)
            if not preserve_partial_anchor:
                self._legend_anchor_x_draft = ""
                self._legend_anchor_y_draft = ""
        _set_line_edit_text(
            self._canvas_color_edit,
            self._plot_style_extras.get("figure_facecolor") or self._plot_style_extras.get("axes_facecolor"),
            allow_blank=True,
        )
        canvas_alpha = _safe_float(self._plot_style_extras.get("figure_facealpha"))
        if canvas_alpha is None:
            canvas_alpha = _safe_float(self._plot_style_extras.get("axes_facealpha"))
        self._set_alpha_slider_value(
            self._canvas_alpha_slider,
            self._canvas_alpha_value_label,
            canvas_alpha,
            default_alpha=_CANVAS_ALPHA_DEFAULT,
        )
        _set_line_edit_text(self._spine_width_edit, self._plot_style_extras.get("spine_width"), allow_blank=True)

    def _apply_figure_state(self, state: FigureState, *, apply_extra_controls: bool = True) -> None:
        self._figure_state = state
        self._refresh_template_combo()

        _set_line_edit_text(self._x_label_edit, state.x_label)
        _set_line_edit_text(self._y_label_edit, state.y_label)
        _set_line_edit_text(self._x_min_edit, state.x_min, allow_blank=True)
        _set_line_edit_text(self._x_max_edit, state.x_max, allow_blank=True)
        _set_line_edit_text(self._y_min_edit, state.y_min, allow_blank=True)
        _set_line_edit_text(self._y_max_edit, state.y_max, allow_blank=True)
        self._refresh_font_family_combo(state.font_family)
        _set_line_edit_text(self._font_size_edit, state.font_size)
        _set_line_edit_text(self._legend_font_size_edit, state.legend_font_size)
        _set_line_edit_text(self._figure_width_edit, state.figure_width)
        _set_line_edit_text(self._figure_height_edit, state.figure_height)
        _set_line_edit_text(self._dpi_edit, state.dpi)
        _set_line_edit_text(self._plot_line_width_edit, state.line_width)
        _set_line_edit_text(self._plot_marker_size_edit, state.marker_size)
        self._set_alpha_slider_value(
            self._grid_alpha_slider,
            self._grid_alpha_value_label,
            state.grid_alpha,
            default_alpha=_GRID_ALPHA_DEFAULT,
        )
        _set_line_edit_text(self._grid_line_width_edit, state.grid_line_width)

        self._errbar_cb.blockSignals(True)
        self._errbar_cb.setChecked(state.show_errbar)
        self._errbar_cb.blockSignals(False)
        self._x_log_cb.blockSignals(True)
        self._x_log_cb.setChecked(state.x_log)
        self._x_log_cb.blockSignals(False)
        self._y_log_cb.blockSignals(True)
        self._y_log_cb.setChecked(state.y_log)
        self._y_log_cb.blockSignals(False)
        self._grid_cb.blockSignals(True)
        self._grid_cb.setChecked(state.grid)
        self._grid_cb.blockSignals(False)
        legend_idx = self._legend_pos_combo.findText(state.legend_pos or "best")
        self._legend_pos_combo.blockSignals(True)
        if legend_idx >= 0:
            self._legend_pos_combo.setCurrentIndex(legend_idx)
        self._legend_pos_combo.blockSignals(False)
        if apply_extra_controls:
            self._apply_plot_style_extra_controls()
        theme = global_assets.get_plot_theme(state.theme)
        self._current_plot_theme_id = theme.id if theme is not None else None
        self._theme_hint_label.setText(_THEME_HINTS.get(state.theme, ""))
        self._update_template_summary()
        self._sync_canvas_display_geometry(state)

    @staticmethod
    def _fitted_canvas_size(available_width: int, available_height: int, aspect_ratio: float) -> tuple[int, int]:
        safe_width = max(1, available_width)
        safe_height = max(1, available_height)
        safe_ratio = max(0.05, aspect_ratio)
        target_width = safe_width
        target_height = target_width / safe_ratio
        if target_height > safe_height:
            target_height = safe_height
            target_width = target_height * safe_ratio
        return max(1, int(round(target_width))), max(1, int(round(target_height)))

    def _sync_canvas_display_geometry(self, state: Optional[FigureState] = None) -> None:
        if not HAS_MATPLOTLIB or self._figure is None or self._canvas is None or self._canvas_host is None:
            return
        state = state or self._figure_state
        aspect_ratio = max(0.1, state.figure_width) / max(0.1, state.figure_height)
        host_rect = self._canvas_host.viewport().contentsRect()
        canvas_width, canvas_height = self._fitted_canvas_size(host_rect.width(), host_rect.height(), aspect_ratio)
        target_size = (canvas_width, canvas_height)
        if target_size != self._display_canvas_size:
            self._display_canvas_size = target_size
            self._canvas.setFixedSize(canvas_width, canvas_height)
            self._canvas.updateGeometry()
        self._figure.set_dpi(self._display_dpi)
        self._figure.set_size_inches(canvas_width / self._display_dpi, canvas_height / self._display_dpi, forward=False)

    def _fallback_layout_margins(self, state: Optional[FigureState] = None) -> dict[str, float]:
        state = state or self._figure_state
        if self._figure is None:
            return {"left": 0.14, "right": 0.97, "top": 0.95, "bottom": 0.12}

        width_inch, height_inch = self._figure.get_size_inches()
        figure_dpi = max(1.0, self._figure.get_dpi())
        width_px = width_inch * figure_dpi
        height_px = height_inch * figure_dpi
        font_padding = max(0.0, state.font_size - 10)

        left = min(0.24, 0.12 + font_padding * 0.003)
        bottom = min(0.22, 0.11 + font_padding * 0.0035)
        top = max(0.84, 0.97 - font_padding * 0.002)
        right = 0.97

        if width_px < 520:
            left = max(left, 0.16)
            right = min(right, 0.95)
        if width_px < 380:
            left = max(left, 0.20)
            right = min(right, 0.94)
        if height_px < 360:
            bottom = max(bottom, 0.15)
            top = min(top, 0.94)
        if height_px < 260:
            bottom = max(bottom, 0.18)
            top = min(top, 0.92)
        if state.legend_pos in {"center left", "upper left", "lower left"}:
            left = max(left, 0.15)

        return {
            "left": left,
            "right": right,
            "top": top,
            "bottom": bottom,
        }

    def _apply_figure_layout(self, state: Optional[FigureState] = None) -> None:
        if not HAS_MATPLOTLIB or self._figure is None:
            return

        state = state or self._figure_state
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "error",
                    message="Tight layout not applied.*",
                    category=UserWarning,
                )
                self._figure.tight_layout(pad=1.1)
                return
        except Exception:
            pass

        self._figure.subplots_adjust(**self._fallback_layout_margins(state))

    def _sync_state_from_controls(self) -> FigureState:
        self._figure_state = FigureState(
            theme=self._figure_state.theme or "默认",
            x_label=self._x_label_edit.text().strip() or "X",
            y_label=self._y_label_edit.text().strip() or "Y",
            figure_width=max(0.1, _safe_float_or(self._figure_width_edit.text(), self._figure_state.figure_width)),
            figure_height=max(0.1, _safe_float_or(self._figure_height_edit.text(), self._figure_state.figure_height)),
            dpi=max(1, _safe_int_or(self._dpi_edit.text(), self._figure_state.dpi)),
            show_errbar=self._errbar_cb.isChecked(),
            x_min=_safe_float(self._x_min_edit.text()),
            x_max=_safe_float(self._x_max_edit.text()),
            y_min=_safe_float(self._y_min_edit.text()),
            y_max=_safe_float(self._y_max_edit.text()),
            x_log=self._x_log_cb.isChecked(),
            y_log=self._y_log_cb.isChecked(),
            grid=self._grid_cb.isChecked(),
            grid_alpha=self._alpha_from_slider_value(self._grid_alpha_slider.value()),
            grid_line_width=max(0.0, _safe_float_or(self._grid_line_width_edit.text(), self._figure_state.grid_line_width)),
            legend_pos=self._legend_pos_combo.currentText() or self._figure_state.legend_pos,
            font_size=max(1, _safe_int_or(self._font_size_edit.text(), self._figure_state.font_size)),
            font_family="" if self._font_family_combo.currentText() == "默认" else self._font_family_combo.currentText().strip(),
            legend_font_size=max(1, _safe_int_or(self._legend_font_size_edit.text(), self._figure_state.legend_font_size)),
            line_width=max(0.1, _safe_float_or(self._plot_line_width_edit.text(), self._figure_state.line_width)),
            marker_size=max(0.1, _safe_float_or(self._plot_marker_size_edit.text(), self._figure_state.marker_size)),
        )
        return self._figure_state

    def _on_quick_config_changed(self) -> None:
        previous_state_payload = self._figure_state.model_dump()
        previous_extra_payload = copy.deepcopy(self._plot_style_extras)
        state = self._sync_state_from_controls()
        state_payload = state.model_dump()
        changed_keys = {
            key for key, value in state_payload.items()
            if previous_state_payload.get(key) != value
        }
        extra_options = self._plot_style_extra_options_from_controls()
        changed_extra_paths = _nested_mapping_changed_paths(previous_extra_payload, extra_options)
        self._apply_base_plot_style_options(
            {key: state_payload[key] for key in changed_keys},
            changed_keys=changed_keys,
            extra_options=extra_options,
            changed_extra_paths=changed_extra_paths,
        )
        self._theme_hint_label.setText(_THEME_HINTS.get(self._figure_state.theme, ""))
        self._redraw()

    def _selected_curve(self) -> Optional[dict]:
        return self._curve_from_item(self._chart_list.currentItem())


    def _selected_curves(self) -> list[dict]:
        """Return all selected curves."""
        items = self._chart_list.selectedItems()
        return [c for item in items if (c := self._curve_from_item(item)) is not None]

    def _set_selected_visibility(self, visible: bool) -> None:
        """Unified helper: set visibility of selected curves."""
        for curve in self._selected_curves():
            curve["visible"] = visible
            self._record_curve_style_changes(self._curve_key(curve), {"visible"})
        self._refresh_chart_list()
        self._redraw_now()

    def _show_all_curves(self) -> None:
        """Show all curves."""
        for curve in self._chart_series:
            curve["visible"] = True
            self._record_curve_style_changes(self._curve_key(curve), {"visible"})
        self._refresh_chart_list()
        self._redraw_now()

    def _invert_curve_visibility(self) -> None:
        """Invert visibility for all curves."""
        for curve in self._chart_series:
            curve["visible"] = not bool(curve.get("visible", True))
            self._record_curve_style_changes(self._curve_key(curve), {"visible"})
        self._refresh_chart_list()
        self._redraw_now()

    def _find_chart_curve(self, curve_key: str) -> Optional[dict]:
        for curve in self._chart_series:
            if self._curve_key(curve) == curve_key:
                return curve
        return None

    def _curve_from_item(self, item) -> Optional[dict]:
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        curve_key = ""
        if isinstance(data, dict):
            curve_key = self._curve_key(data)
        else:
            curve_key = str(data or "")
        if curve_key:
            resolved = self._find_chart_curve(curve_key)
            if resolved is not None:
                return resolved
        return data if isinstance(data, dict) else None

    def _set_curve_display_name(self, curve: dict, display_name: str) -> None:
        curve["display_name"] = display_name.strip() or curve.get("name", "")
        self._refresh_chart_list()
        self._redraw_now()

    def _reset_curve_display_name(self, curve: dict) -> None:
        curve["display_name"] = curve.get("name", "")
        self._refresh_chart_list()
        self._redraw_now()

    def _rename_selected_curve_display_name(self) -> None:
        curve = self._selected_curve()
        if curve is None:
            return
        current_name = self._curve_display_name(curve)
        new_name, ok = TextInputDialog.get_text(self, "重命名图例显示名称", "显示名称:", text=current_name)
        if not ok or not new_name.strip():
            return
        self._set_curve_display_name(curve, new_name)

    def _on_chart_list_context_menu(self, pos) -> None:
        item = self._chart_list.itemAt(pos)
        if item is None:
            return
        self._chart_list.setCurrentItem(item)
        curve = self._curve_from_item(item)
        if curve is None:
            return
        menu = RoundMenu(parent=self)
        rename_action = Action(FIF.EDIT, "重命名显示名称")
        rename_action.triggered.connect(self._rename_selected_curve_display_name)
        menu.addAction(rename_action)
        reset_action = Action(FIF.SYNC, "恢复原始名称")
        reset_action.setEnabled(self._curve_display_name(curve) != (curve.get("name") or ""))
        reset_action.triggered.connect(lambda checked=False: self._reset_curve_display_name(curve))
        menu.addAction(reset_action)

        menu.addSeparator()
        hide_action = Action(getattr(FIF, 'CANCEL', FIF.CLOSE), '隐藏已选中')
        hide_action.triggered.connect(lambda: self._set_selected_visibility(False))
        menu.addAction(hide_action)
        show_action = Action(FIF.VIEW, '显示已选中')
        show_action.triggered.connect(lambda: self._set_selected_visibility(True))
        menu.addAction(show_action)
        show_only_action = Action(getattr(FIF, 'VIEW', FIF.SEARCH), '仅显示选中')
        show_only_action.triggered.connect(self._show_only_selected_curve)
        menu.addAction(show_only_action)
        show_all_action = Action(FIF.ZOOM_FIT, '全部显示')
        show_all_action.triggered.connect(self._show_all_curves)
        menu.addAction(show_all_action)
        invert_action = Action(getattr(FIF, 'SYNC', FIF.SYNC), '反选显示状态')
        invert_action.triggered.connect(self._invert_curve_visibility)
        menu.addAction(invert_action)
        menu.exec(self._chart_list.mapToGlobal(pos))

    def _show_only_selected_curve(self):
        selected_curve = self._selected_curve()
        if selected_curve is None:
            return
        selected_key = self._curve_key(selected_curve)
        for curve in self._chart_series:
            curve["visible"] = (self._curve_key(curve) == selected_key)
        self._refresh_chart_list()
        self._redraw_now()

    def _refresh_chart_list(self) -> None:
        current_name = self._style_target
        current_identity = None
        current_curve = self._selected_curve()
        if current_curve is not None:
            current_name = current_curve.get("name")
            current_identity = self._curve_identity(current_curve)

        self._chart_list.blockSignals(True)
        self._chart_list.clear()
        current_item = None
        for curve in self._chart_series:
            path_label = self._curve_list_label(curve)
            label = path_label if curve.get("visible", True) else f"[隐藏] {path_label}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, self._curve_key(curve))
            item.setToolTip(path_label if path_label not in {"—", "未关联项目树"} else self._curve_display_name(curve))
            if not curve.get("visible", True):
                item.setForeground(QColor("#888888"))
            self._chart_list.addItem(item)
            if current_identity and self._curve_identity(curve) == current_identity:
                current_item = item
            elif current_item is None and current_name and curve["name"] == current_name:
                current_item = item
        if current_item is None and self._chart_list.count() > 0:
            current_item = self._chart_list.item(0)
        if current_item is not None:
            self._chart_list.setCurrentItem(current_item)
        self._chart_list.blockSignals(False)

        if current_item is not None:
            self._on_current_changed(current_item, None)
        else:
            self._set_style_enabled(False)
            self._update_selected_curve_path_label(None)
            self._refresh_plot_extension_list()
            self._refresh_style_extension_panel()
        self._update_visibility_button()

    def _update_visibility_button(self) -> None:
        curve = self._selected_curve()
        if curve is None:
            self._btn_toggle_visible.setEnabled(False)
            self._btn_toggle_visible.setIcon(_ICON_HIDE.icon())
            self._update_chart_order_buttons()
            return
        visible = bool(curve.get("visible", True))
        self._btn_toggle_visible.setEnabled(True)
        self._btn_toggle_visible.setIcon((_ICON_HIDE if visible else _ICON_SHOW).icon())
        self._btn_toggle_visible.setToolTip("隐藏当前曲线" if visible else "显示当前曲线")
        self._update_chart_order_buttons()

    def _selected_curve_index(self) -> int:
        curve = self._selected_curve()
        if curve is None:
            return -1
        curve_identity = self._curve_identity(curve)
        for index, item in enumerate(self._chart_series):
            if self._curve_identity(item) == curve_identity:
                return index
        return -1

    def _update_chart_order_buttons(self) -> None:
        if not hasattr(self, "_btn_selected_up") or not hasattr(self, "_btn_selected_down"):
            return
        index = self._selected_curve_index()
        has_curve = index >= 0
        self._btn_selected_up.setEnabled(has_curve and index > 0)
        self._btn_selected_down.setEnabled(has_curve and index < len(self._chart_series) - 1)

    def _on_clear_chart(self) -> None:
        self._chart_series.clear()
        self._curve_styles.clear()
        self._curve_style_change_versions.clear()
        self._style_target = None
        self._refresh_chart_list()
        self._redraw_now()

    def _on_remove_selected(self) -> None:
        curve = self._selected_curve()
        if curve is None:
            return
        target_key = self._curve_key(curve)
        self._chart_series = [item for item in self._chart_series if self._curve_key(item) != target_key]
        self._curve_styles.pop(target_key, None)
        self._curve_style_change_versions.pop(target_key, None)
        if self._style_target == target_key:
            self._style_target = None
        self._refresh_chart_list()
        self._redraw_now()

    def _move_selected_curve_up(self) -> None:
        self._move_selected_curve("up")

    def _move_selected_curve_down(self) -> None:
        self._move_selected_curve("down")

    def _move_selected_curve(self, direction: str) -> None:
        current_index = self._selected_curve_index()
        if current_index < 0:
            return
        if direction == "up":
            target_index = current_index - 1
        elif direction == "down":
            target_index = current_index + 1
        else:
            return
        if not (0 <= target_index < len(self._chart_series)):
            return
        self._chart_series[current_index], self._chart_series[target_index] = (
            self._chart_series[target_index],
            self._chart_series[current_index],
        )
        self._refresh_chart_list()
        self._redraw_now()

    def _toggle_selected_visibility(self) -> None:
        selected_items = self._chart_list.selectedItems()
        if not selected_items:
            return
        # 以第一个选中项的 visible 状态为基准，全部反转
        first_curve = self._curve_from_item(selected_items[0])
        if first_curve is None:
            return
        new_visible = not bool(first_curve.get("visible", True))
        for item in selected_items:
            curve = self._curve_from_item(item)
            if curve is not None:
                curve["visible"] = new_visible
                self._record_curve_style_changes(self._curve_key(curve), {"visible"})
        self._refresh_chart_list()
        self._redraw_now()

    def _redraw(self) -> None:
        self._redraw_timer.start()

    def request_redraw(self) -> None:
        self._redraw()

    @staticmethod
    def _apply_text_style(text_obj, *, font_family: str, font_size: int, color: Optional[str] = None) -> None:
        if text_obj is None:
            return
        text_obj.set_fontsize(max(1, font_size))
        if font_family:
            text_obj.set_fontfamily(font_family)
        if color is not None:
            text_obj.set_color(color)

    def _apply_axis_text_style(self, axis, state: FigureState, fg: str) -> None:
        axis.tick_params(colors=fg, labelcolor=fg, labelsize=state.font_size)
        self._apply_text_style(axis.xaxis.label, font_family=state.font_family, font_size=state.font_size, color=fg)
        self._apply_text_style(axis.yaxis.label, font_family=state.font_family, font_size=state.font_size, color=fg)
        self._apply_text_style(axis.title, font_family=state.font_family, font_size=state.font_size, color=fg)
        self._apply_text_style(axis.xaxis.get_offset_text(), font_family=state.font_family, font_size=state.font_size, color=fg)
        self._apply_text_style(axis.yaxis.get_offset_text(), font_family=state.font_family, font_size=state.font_size, color=fg)
        for tick_label in [*axis.get_xticklabels(), *axis.get_yticklabels()]:
            self._apply_text_style(tick_label, font_family=state.font_family, font_size=state.font_size, color=fg)

    @staticmethod
    def _positive_axis_bound(values: List[Any], *, prefer_max: bool = False) -> Optional[float]:
        positives: List[float] = []
        for value in values:
            number = _safe_float(value)
            if number is None or number <= 0:
                continue
            positives.append(number)
        if not positives:
            return None
        return max(positives) if prefer_max else min(positives)

    def _sanitize_log_axis_limits(
        self,
        values: List[Any],
        lower: Optional[float],
        upper: Optional[float],
    ) -> tuple[Optional[float], Optional[float], bool]:
        min_positive = self._positive_axis_bound(values)
        max_positive = self._positive_axis_bound(values, prefer_max=True)
        if min_positive is None or max_positive is None:
            return lower, upper, False

        safe_lower = lower if lower is not None and lower > 0 else min_positive
        safe_upper = upper if upper is not None and upper > 0 else max_positive
        if safe_upper <= safe_lower:
            safe_upper = max_positive if max_positive > safe_lower else safe_lower * 10.0
        return safe_lower, safe_upper, True

    def _redraw_now(self) -> None:
        if not HAS_MATPLOTLIB or self._figure is None or self._canvas is None:
            return

        self._redraw_timer.stop()
        manual_state = self._sync_state_from_controls().model_copy(deep=True)
        manual_state_payload = manual_state.model_dump()
        manual_plot_style_extras = copy.deepcopy(self._plot_style_extras)
        base_curve_style_payloads: Dict[str, Dict[str, Any]] = {}
        context_curve_style_payloads: Dict[str, Dict[str, Any]] = {}
        for curve in self._chart_series:
            curve_identity = self._curve_identity(curve)
            base_curve_style_payloads[curve_identity] = {
                **copy.deepcopy(self._curve_styles.get(self._curve_key(curve), {})),
                "visible": bool(curve.get("visible", True)),
            }
            context_curve_style_payloads[curve_identity] = self._current_curve_style_payload(curve)

        self._sync_canvas_display_geometry(manual_state)
        self._figure.clear()
        axis = self._figure.add_subplot(111)
        self._apply_preview_host_background()
        base_bg, base_fg, base_grid_color = self._theme_palette_for_state(manual_state)

        selected_curve = self._selected_curve()
        initial_visible_series = [
            curve for curve in self._chart_series
            if base_curve_style_payloads.get(self._curve_identity(curve), {}).get("visible", True)
        ]
        bw_colors = ["#000000", "#444444", "#888888", "#aaaaaa"]
        bw_index = 0
        reserved_curve_keys = {
            "color", "linestyle", "marker", "linewidth", "marker_size", "alpha", "markevery", "dash_scale", "visible",
        }
        plotted_series: List[dict] = []

        plot_context = PlotExtensionContext(
            figure=self._figure,
            canvas=self._canvas,
            axis=axis,
            axes=[axis],
            visible_series=self._plot_context_series_entries(initial_visible_series, context_curve_style_payloads),
            plotted_series=plotted_series,
            selected_series=(
                self._plot_context_series_entry(
                    selected_curve,
                    style_payload=context_curve_style_payloads.get(self._curve_identity(selected_curve), {}),
                )
                if selected_curve is not None
                else None
            ),
            selected_series_identity=(self._curve_identity(selected_curve) if selected_curve is not None else None),
            figure_state=copy.deepcopy(manual_state_payload),
            plot_style_extras=copy.deepcopy(manual_plot_style_extras),
            theme_colors={"background": base_bg, "foreground": base_fg, "grid": base_grid_color},
        )
        extension_style_layers: List[Dict[str, Any]] = []

        for applied in list(self._applied_plot_extensions):
            type_id = str(applied.get("type") or "")
            extension = extension_registry.get_plot(type_id)
            if extension is None:
                continue
            target_curve = self._resolve_plot_extension_curve(applied.get("curve_identity"))
            plot_context.clear_style_patches()
            plot_context.selected_series = (
                self._plot_context_series_entry(
                    target_curve,
                    style_payload=context_curve_style_payloads.get(self._curve_identity(target_curve), {}),
                )
                if target_curve is not None
                else None
            )
            plot_context.selected_series_identity = self._curve_identity(target_curve) if target_curve is not None else applied.get("curve_identity")
            try:
                plot_context.phase = "before_plot"
                invoke_plot_extension_handler(extension, plot_context, dict(applied.get("options") or {}))
            except Exception:
                continue
            extension_style_layers.append({
                "sequence": int(applied.get("sequence") or 0),
                "figure_state": copy.deepcopy(plot_context.figure_state_patch),
                "plot_style_extras": copy.deepcopy(plot_context.plot_style_patch),
                "curve_styles": copy.deepcopy(plot_context.curve_style_patches),
            })
            plot_context.refresh_axes()

        effective_state_payload = self._effective_plot_figure_state_payload(manual_state_payload, extension_style_layers)
        effective_plot_style_extras = self._effective_plot_style_extras(manual_plot_style_extras, extension_style_layers)
        effective_curve_style_payloads = self._effective_curve_style_payloads(base_curve_style_payloads, extension_style_layers)
        state = FigureState(**effective_state_payload)
        self._sync_canvas_display_geometry(state)
        bg, fg, grid_color = self._theme_palette_for_state(state)
        figure_facecolor = effective_plot_style_extras.get("figure_facecolor")
        figure_facealpha = _safe_float(effective_plot_style_extras.get("figure_facealpha"))
        axes_facecolor = effective_plot_style_extras.get("axes_facecolor") or figure_facecolor
        axes_facealpha = _safe_float(effective_plot_style_extras.get("axes_facealpha"))
        if axes_facealpha is None:
            axes_facealpha = figure_facealpha
        visible_series = [
            curve for curve in self._chart_series
            if effective_curve_style_payloads.get(self._curve_identity(curve), {}).get("visible", True)
        ]
        default_line_kwargs = dict(effective_plot_style_extras.get("line_defaults", {}) or {})
        errorbar_kwargs = dict(effective_plot_style_extras.get("errorbar_kwargs", {}) or {})
        plot_context.figure_state = copy.deepcopy(effective_state_payload)
        plot_context.plot_style_extras = copy.deepcopy(effective_plot_style_extras)
        plot_context.theme_colors = {"background": bg, "foreground": fg, "grid": grid_color}
        plot_context.visible_series = self._plot_context_series_entries(visible_series, effective_curve_style_payloads)
        plot_context.selected_series = (
            self._plot_context_series_entry(
                selected_curve,
                style_payload=effective_curve_style_payloads.get(self._curve_identity(selected_curve), {}),
            )
            if selected_curve is not None
            else None
        )
        plot_context.selected_series_identity = self._curve_identity(selected_curve) if selected_curve is not None else None

        axis = plot_context.axis
        if axis is None:
            axis = self._figure.add_subplot(111)
            plot_context.set_active_axis(axis)

        self._figure.patch.set_facecolor(_color_with_alpha(figure_facecolor or bg, figure_facealpha))
        if axis is not None and not plot_context.skip_default_formatting:
            axis.set_facecolor(_color_with_alpha(axes_facecolor or bg, axes_facealpha))
            spine_width = _safe_float(effective_plot_style_extras.get("spine_width"))
            spine_visibility = dict(effective_plot_style_extras.get("spine_visibility", {}) or {})
            for spine_name, spine in axis.spines.items():
                spine.set_edgecolor(fg)
                if spine_name in spine_visibility:
                    spine.set_visible(bool(spine_visibility.get(spine_name)))
                if spine_width is not None:
                    spine.set_linewidth(max(0.1, spine_width))

            grid_kwargs = {
                "color": grid_color,
                "linestyle": "--",
                "linewidth": state.grid_line_width,
                "alpha": state.grid_alpha,
            }
            grid_kwargs.update(dict(effective_plot_style_extras.get("grid_kwargs", {}) or {}))
            if state.grid:
                axis.grid(True, **grid_kwargs)
            else:
                axis.grid(False)

        if not plot_context.skip_default_plot and axis is not None:
            for curve in visible_series:
                curve_identity = self._curve_identity(curve)
                display_name = self._curve_display_name(curve)
                style_overrides = dict(effective_curve_style_payloads.get(curve_identity, {}))
                color = style_overrides.get("color") or curve.get("color")
                linestyle = style_overrides.get("linestyle", "-")
                marker = style_overrides.get("marker", "")
                line_width = _safe_float_or(style_overrides.get("linewidth"), state.line_width)
                marker_size = _safe_float_or(style_overrides.get("marker_size"), state.marker_size)
                markevery = max(1, _safe_int_or(style_overrides.get("markevery"), 1))
                dash_scale = _safe_float_or(style_overrides.get("dash_scale"), 1.0)
                alpha = _safe_float_or(style_overrides.get("alpha"), 1.0)
                extra_plot_kwargs = {key: value for key, value in style_overrides.items() if key not in reserved_curve_keys}

                plot_kwargs = dict(default_line_kwargs)
                plot_kwargs.update({
                    "label": display_name,
                    "linestyle": linestyle or "none",
                    "linewidth": line_width,
                    "alpha": alpha,
                })
                if marker:
                    plot_kwargs["marker"] = marker
                    plot_kwargs["markersize"] = marker_size
                    if markevery > 1:
                        plot_kwargs["markevery"] = markevery
                plot_kwargs.update(extra_plot_kwargs)
                if state.theme == "简洁黑白":
                    plot_kwargs["color"] = bw_colors[bw_index % len(bw_colors)]
                    bw_index += 1
                elif color:
                    plot_kwargs["color"] = color
                if linestyle in ("--", ":", "-.") and dash_scale != 1.0:
                    base_dashes = {"--": [6, 4], ":": [1, 2], "-.": [8, 3, 1, 3]}.get(linestyle)
                    if base_dashes:
                        plot_kwargs["dashes"] = [segment * dash_scale for segment in base_dashes]

                x_values = list(curve.get("x", []))
                y_values = list(curve.get("y", []))
                y_err = list(curve.get("y_err", []) or [])
                render_x_values, render_y_values, render_indices = decimate_xy_for_rendering(
                    x_values,
                    y_values,
                    _CHART_RENDER_DECIMATION_POLICY,
                )
                render_y_err = [y_err[index] for index in render_indices] if len(y_err) == len(x_values) else []
                plotted_series.append({
                    **curve,
                    "curve_identity": curve_identity,
                    "display_name": display_name,
                    "style": dict(style_overrides),
                })
                if state.show_errbar and render_y_err:
                    axis.errorbar(render_x_values, render_y_values, yerr=render_y_err, capsize=3, **errorbar_kwargs, **plot_kwargs)
                else:
                    axis.plot(render_x_values, render_y_values, **plot_kwargs)

        legend = None
        if visible_series and not plot_context.skip_default_plot and axis is not None and not plot_context.skip_default_formatting:
            legend_style_kwargs = dict(effective_plot_style_extras.get("legend_kwargs", {}) or {})
            legend_edge_alpha = _safe_float(legend_style_kwargs.get("edgealpha"))
            legend_face_alpha = _safe_float(legend_style_kwargs.get("facealpha"))
            legacy_frame_alpha = _safe_float(legend_style_kwargs.get("framealpha"))
            legend_kwargs: Dict[str, Any] = {
                "facecolor": bg,
                "edgecolor": fg,
                "labelcolor": fg,
                "loc": state.legend_pos or "best",
            }
            if state.font_family:
                legend_kwargs["prop"] = {"family": state.font_family, "size": state.legend_font_size}
            else:
                legend_kwargs["fontsize"] = state.legend_font_size
            legend_call_kwargs = dict(legend_style_kwargs)
            if legend_edge_alpha is not None or legend_face_alpha is not None:
                legend_call_kwargs.pop("framealpha", None)
            legend_call_kwargs.pop("edgealpha", None)
            legend_call_kwargs.pop("facealpha", None)
            legend_kwargs.update(legend_call_kwargs)
            legend_anchor = legend_kwargs.get("bbox_to_anchor")
            if isinstance(legend_anchor, (list, tuple)) and len(legend_anchor) >= 2:
                legend_kwargs["bbox_to_anchor"] = (float(legend_anchor[0]), float(legend_anchor[1]))
            legend = axis.legend(
                **legend_kwargs,
            )

        if axis is not None and not plot_context.skip_default_formatting:
            axis.set_xlabel(state.x_label or "X")
            axis.set_ylabel(state.y_label or "Y")
            x_min = state.x_min
            x_max = state.x_max
            y_min = state.y_min
            y_max = state.y_max
            if state.x_log:
                x_min, x_max, use_x_log = self._sanitize_log_axis_limits(
                    [value for curve in visible_series for value in curve.get("x", [])],
                    x_min,
                    x_max,
                )
                if use_x_log:
                    axis.set_xscale("log")
            if state.y_log:
                y_min, y_max, use_y_log = self._sanitize_log_axis_limits(
                    [value for curve in visible_series for value in curve.get("y", [])],
                    y_min,
                    y_max,
                )
                if use_y_log:
                    axis.set_yscale("log")
            if x_min is not None or x_max is not None:
                axis.set_xlim(left=x_min, right=x_max)
            if y_min is not None or y_max is not None:
                axis.set_ylim(bottom=y_min, top=y_max)

            axis_kwargs = dict(effective_plot_style_extras.get("axis_kwargs", {}) or {})
            if axis_kwargs:
                axis.set(**axis_kwargs)

            self._apply_axis_text_style(axis, state, fg)
            tick_params = dict(effective_plot_style_extras.get("tick_params", {}) or {})
            if tick_params:
                axis.tick_params(**tick_params)
            if legend is not None:
                legend_frame = legend.get_frame()
                if legend_edge_alpha is not None or legend_face_alpha is not None:
                    legend_frame.set_alpha(None)
                if legend_edge_alpha is not None:
                    legend_frame.set_edgecolor(_color_with_alpha(legend_frame.get_edgecolor(), legend_edge_alpha))
                elif legend_face_alpha is not None and legacy_frame_alpha is not None:
                    legend_frame.set_edgecolor(_color_with_alpha(legend_frame.get_edgecolor(), legacy_frame_alpha))
                if legend_face_alpha is not None:
                    legend_frame.set_facecolor(_color_with_alpha(legend_frame.get_facecolor(), legend_face_alpha))
                for text in legend.get_texts():
                    self._apply_text_style(text, font_family=state.font_family, font_size=state.legend_font_size, color=fg)
                self._apply_text_style(legend.get_title(), font_family=state.font_family, font_size=state.legend_font_size, color=fg)

        for applied in list(self._applied_plot_extensions):
            type_id = str(applied.get("type") or "")
            extension = extension_registry.get_plot(type_id)
            if extension is None:
                continue
            target_curve = self._resolve_plot_extension_curve(applied.get("curve_identity"))
            try:
                plot_context.clear_style_patches()
                plot_context.phase = "after_plot"
                plot_context.axis = axis
                plot_context.selected_series = (
                    self._plot_context_series_entry(
                        target_curve,
                        style_payload=effective_curve_style_payloads.get(self._curve_identity(target_curve), {}),
                    )
                    if target_curve is not None
                    else None
                )
                plot_context.selected_series_identity = self._curve_identity(target_curve) if target_curve is not None else applied.get("curve_identity")
                invoke_plot_extension_handler(extension, plot_context, dict(applied.get("options") or {}))
            except Exception:
                continue
            plot_context.refresh_axes()

        axis = plot_context.axis or axis

        if not plot_context.skip_default_layout:
            self._apply_figure_layout(state)
            subplot_adjust = effective_plot_style_extras.get("subplot_adjust")
            if isinstance(subplot_adjust, dict) and subplot_adjust:
                self._figure.subplots_adjust(**subplot_adjust)
        self._canvas.draw()
        self._canvas.updateGeometry()
        self._sync_chart_preview_nav_toggle_states()

    def _on_current_changed(self, current, _prev) -> None:
        curve = self._curve_from_item(current)
        if current is None:
            self._set_style_enabled(False)
        else:
            self._set_style_enabled(True, curve)
        self._update_selected_curve_path_label(curve)
        self._update_visibility_button()
        self._refresh_style_extension_panel()

    def _set_style_enabled(self, enabled: bool, curve: Optional[dict] = None) -> None:
        self._style_color_btn.setEnabled(enabled)
        self._style_reset_color_btn.setEnabled(enabled)
        self._style_line_combo.setEnabled(enabled)
        self._style_line_width_edit.setEnabled(enabled)
        self._style_opacity_slider.setEnabled(enabled)
        self._style_dash_scale_edit.setEnabled(enabled)
        self._style_marker_size_edit.setEnabled(enabled)
        self._style_density_edit.setEnabled(enabled)
        self._style_visible_cb.setEnabled(enabled)
        self._btn_load_curve_style_template.setEnabled(enabled)
        self._btn_save_curve_style_template.setEnabled(enabled)
        if enabled and curve:
            self._style_target = self._curve_key(curve)
            display_name = self._curve_display_name(curve)
            self._style_target_label.setText(f"当前选中：{display_name}")
            self._style_target_label.setToolTip(display_name)
            style = self._current_curve_style(curve)
            if style is None:
                return
            self._update_color_btn(style.color or curve.get("color") or "#888888")
            try:
                idx = next(
                    index for index, (line_style, marker_style) in enumerate(zip(_STYLE_LINESTYLES, _STYLE_MARKERS))
                    if line_style == style.linestyle and marker_style == style.marker
                )
            except StopIteration:
                idx = 0
            self._style_line_combo.blockSignals(True)
            self._style_line_combo.setCurrentIndex(idx)
            self._style_line_combo.blockSignals(False)
            self._style_line_width_edit.blockSignals(True)
            self._style_line_width_edit.setText(f"{style.linewidth:g}")
            self._style_line_width_edit.blockSignals(False)
            self._style_opacity_slider.blockSignals(True)
            self._style_opacity_slider.setValue(self._alpha_slider_value(style.alpha))
            self._style_opacity_slider.blockSignals(False)
            self._update_style_opacity_value_label(self._style_opacity_slider.value())
            self._style_dash_scale_edit.blockSignals(True)
            self._style_dash_scale_edit.setText(f"{style.dash_scale:g}")
            self._style_dash_scale_edit.blockSignals(False)
            self._style_marker_size_edit.blockSignals(True)
            self._style_marker_size_edit.setText(f"{style.marker_size:g}")
            self._style_marker_size_edit.blockSignals(False)
            self._style_density_edit.blockSignals(True)
            self._style_density_edit.setText(str(style.markevery))
            self._style_density_edit.blockSignals(False)
            self._style_visible_cb.blockSignals(True)
            self._style_visible_cb.setChecked(bool(style.visible))
            self._style_visible_cb.blockSignals(False)
        else:
            self._style_target = None
            self._style_target_label.setText("当前选中：未选中")
            self._style_target_label.setToolTip("")
            self._update_color_btn("#888888")
            self._style_line_width_edit.clear()
            self._style_opacity_slider.blockSignals(True)
            self._style_opacity_slider.setValue(self._alpha_slider_value(1.0))
            self._style_opacity_slider.blockSignals(False)
            self._update_style_opacity_value_label(self._style_opacity_slider.value())
            self._style_dash_scale_edit.clear()
            self._style_marker_size_edit.clear()
            self._style_density_edit.clear()
            self._style_visible_cb.blockSignals(True)
            self._style_visible_cb.setChecked(False)
            self._style_visible_cb.blockSignals(False)

    def _on_style_opacity_changed(self, value: int) -> None:
        self._update_style_opacity_value_label(value)
        if self._style_target:
            self._on_style_metrics_changed()

    def _update_color_btn(self, color_str: str) -> None:
        color = QColor(color_str)
        if not color.isValid():
            color = QColor("#888888")
        self._style_color_btn.blockSignals(True)
        self._style_color_btn.setColor(color)
        self._style_color_btn.blockSignals(False)

    def _on_style_color_changed(self, color) -> None:
        if not self._style_target:
            return
        color_obj = color if isinstance(color, QColor) else QColor(str(color))
        if not color_obj.isValid():
            return
        self._apply_base_curve_style_options({"color": color_obj.name(QColor.NameFormat.HexRgb)})
        self._redraw_now()

    def _on_style_reset_color(self) -> None:
        if not self._style_target:
            return
        self._apply_base_curve_style_options({"color": None})
        for curve in self._chart_series:
            if self._curve_key(curve) == self._style_target:
                self._update_color_btn(curve.get("color") or "#888888")
                break
        self._redraw_now()

    def _on_style_line_changed(self, idx: int) -> None:
        if not self._style_target:
            return
        self._apply_base_curve_style_options(
            {
                "linestyle": _STYLE_LINESTYLES[idx],
                "marker": _STYLE_MARKERS[idx],
            }
        )
        self._redraw_now()

    def _on_style_visibility_changed(self, _state: int) -> None:
        if not self._style_target:
            return
        self._apply_base_curve_style_options({"visible": bool(self._style_visible_cb.isChecked())})
        self._redraw_now()

    def _on_style_metrics_changed(self) -> None:
        if not self._style_target:
            return
        density = max(1, _safe_int_or(self._style_density_edit.text(), 1))
        self._apply_base_curve_style_options(
            {
                "linewidth": max(0.1, _safe_float_or(self._style_line_width_edit.text(), self._figure_state.line_width)),
                "alpha": self._alpha_from_slider_value(self._style_opacity_slider.value()),
                "marker_size": max(0.1, _safe_float_or(self._style_marker_size_edit.text(), self._figure_state.marker_size)),
                "markevery": density,
                "dash_scale": max(0.1, _safe_float_or(self._style_dash_scale_edit.text(), 1.0)),
            }
        )
        self._redraw()

    def _on_export_image(self) -> None:
        if not HAS_MATPLOTLIB or self._figure is None:
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出图片",
            "chart.png",
            "PNG (*.png);;SVG (*.svg);;PDF (*.pdf)",
        )
        if not file_path:
            return
        if not self._save_figure_to_path(file_path):
            return
        InfoBar.success("导出成功", file_path, parent=self, position=InfoBarPosition.TOP)

    def _default_picture_export_name(self) -> str:
        if len(self._chart_series) == 1:
            base_name = self._curve_display_name(self._chart_series[0])
        elif self._chart_series:
            base_name = f"chart_{len(self._chart_series)}"
        else:
            base_name = "chart"
        return f"{base_name}.png"

    def _save_figure_to_path(self, file_path: str) -> bool:
        if not HAS_MATPLOTLIB or self._figure is None:
            return False
        display_size = self._figure.get_size_inches()
        display_dpi = self._figure.get_dpi()
        try:
            self._figure.set_dpi(self._figure_state.dpi)
            self._figure.set_size_inches(self._figure_state.figure_width, self._figure_state.figure_height, forward=False)
            self._apply_figure_layout(self._figure_state)
            self._figure.savefig(file_path, dpi=self._figure_state.dpi)
        except Exception as exc:
            InfoBar.error("导出失败", str(exc), parent=self, position=InfoBarPosition.TOP)
            return False
        finally:
            self._figure.set_dpi(display_dpi)
            self._figure.set_size_inches(display_size[0], display_size[1], forward=False)
            self._sync_canvas_display_geometry()
            if self._canvas is not None:
                self._canvas.draw_idle()
        return True

    def _on_export_to_picture_group(self) -> None:
        project = project_manager.current_project
        if project is None:
            InfoBar.warning("提示", "请先打开项目", parent=self, position=InfoBarPosition.TOP)
            return
        if project.file_path is None:
            InfoBar.warning("提示", "请先保存项目，再导出到图片集", parent=self, position=InfoBarPosition.TOP)
            return
        export_plan = choose_picture_export_plan(
            self,
            title="导出到图片集",
            default_export_name=self._default_picture_export_name(),
            preferred_target_node_id=self._selected_tree_id,
            file_suffix=".png",
        )
        if export_plan is None:
            return
        file_path = project_manager.prepare_picture_export_path(
            export_plan.export_name,
            ".png",
            export_plan.target_folder_id,
        )
        if not file_path:
            InfoBar.error("导出失败", "无法确定图片集目录", parent=self, position=InfoBarPosition.TOP)
            return
        if not self._save_figure_to_path(file_path):
            return
        target_folder_id = project_manager.get_picture_target_folder_id(export_plan.target_folder_id)
        node = project_manager.add_picture(
            file_path,
            name=Path(file_path).name,
            parent_id=target_folder_id,
            plot_snapshot=self._build_picture_plot_snapshot(),
        )
        if node is None:
            InfoBar.error("导出失败", "图片记录写入项目失败", parent=self, position=InfoBarPosition.TOP)
            return
        self.project_modified.emit()
        InfoBar.success("已导出到图片集", Path(file_path).name, parent=self, position=InfoBarPosition.TOP)

    def update_theme(self) -> None:
        self._apply_preview_host_background()
        if self._figure is None or self._canvas is None:
            return
        if not self.isVisible():
            self._theme_refresh_pending = True
            return
        self._theme_refresh_pending = False
        self._redraw_timer.start(0)

    @property
    def _chart_series(self):
        return self._workspace_state.chart_series

    @_chart_series.setter
    def _chart_series(self, value):
        self._workspace_state.chart_series = value

    @property
    def _curve_styles(self):
        return self._workspace_state.curve_styles

    @_curve_styles.setter
    def _curve_styles(self, value):
        self._workspace_state.curve_styles = value

    @property
    def _style_target(self):
        return self._workspace_state.style_target

    @_style_target.setter
    def _style_target(self, value):
        self._workspace_state.style_target = value

    @property
    def _figure_state(self):
        return self._workspace_state.figure_state

    @_figure_state.setter
    def _figure_state(self, value):
        self._workspace_state.figure_state = value

    @property
    def _plot_style_refs(self):
        return self._workspace_state.plot_style_refs

    @_plot_style_refs.setter
    def _plot_style_refs(self, value):
        self._workspace_state.plot_style_refs = value

    @property
    def _applied_plot_style_ref(self):
        return self._workspace_state.applied_plot_style_ref

    @_applied_plot_style_ref.setter
    def _applied_plot_style_ref(self, value):
        self._workspace_state.applied_plot_style_ref = value

    @property
    def _active_template_node_id(self):
        return self._workspace_state.active_template_node_id

    @_active_template_node_id.setter
    def _active_template_node_id(self, value):
        self._workspace_state.active_template_node_id = value

    @property
    def _curve_style_template_ids(self):
        return self._workspace_state.curve_style_template_ids

    @_curve_style_template_ids.setter
    def _curve_style_template_ids(self, value):
        self._workspace_state.curve_style_template_ids = value

    @property
    def _active_curve_style_ref(self):
        return self._workspace_state.active_curve_style_ref

    @_active_curve_style_ref.setter
    def _active_curve_style_ref(self, value):
        self._workspace_state.active_curve_style_ref = value

    @property
    def _active_curve_style_template_id(self):
        return self._workspace_state.active_curve_style_template_id

    @_active_curve_style_template_id.setter
    def _active_curve_style_template_id(self, value):
        self._workspace_state.active_curve_style_template_id = value

    @property
    def _current_plot_theme_id(self):
        return self._workspace_state.current_plot_theme_id

    @_current_plot_theme_id.setter
    def _current_plot_theme_id(self, value):
        self._workspace_state.current_plot_theme_id = value

    @property
    def _plot_extension_options(self):
        return self._workspace_state.plot_extension_options

    @_plot_extension_options.setter
    def _plot_extension_options(self, value):
        self._workspace_state.plot_extension_options = value

    @property
    def _applied_plot_extensions(self):
        return self._workspace_state.applied_plot_extensions

    @_applied_plot_extensions.setter
    def _applied_plot_extensions(self, value):
        self._workspace_state.applied_plot_extensions = value

    @property
    def _plot_extension_instance_seed(self):
        return self._workspace_state.plot_extension_instance_seed

    @_plot_extension_instance_seed.setter
    def _plot_extension_instance_seed(self, value):
        self._workspace_state.plot_extension_instance_seed = value

    @property
    def _style_change_sequence(self):
        return self._workspace_state.style_change_sequence

    @_style_change_sequence.setter
    def _style_change_sequence(self, value):
        self._workspace_state.style_change_sequence = value

    @property
    def _figure_state_change_versions(self):
        return self._workspace_state.figure_state_change_versions

    @_figure_state_change_versions.setter
    def _figure_state_change_versions(self, value):
        self._workspace_state.figure_state_change_versions = value

    @property
    def _plot_style_extra_versions(self):
        return self._workspace_state.plot_style_extra_versions

    @_plot_style_extra_versions.setter
    def _plot_style_extra_versions(self, value):
        self._workspace_state.plot_style_extra_versions = value

    @property
    def _curve_style_change_versions(self):
        return self._workspace_state.curve_style_change_versions

    @_curve_style_change_versions.setter
    def _curve_style_change_versions(self, value):
        self._workspace_state.curve_style_change_versions = value

    @property
    def _plot_style_extras(self):
        return self._workspace_state.plot_style_extras

    @_plot_style_extras.setter
    def _plot_style_extras(self, value):
        self._workspace_state.plot_style_extras = value

    @property
    def _legend_anchor_x_draft(self):
        return self._workspace_state.legend_anchor_x_draft

    @_legend_anchor_x_draft.setter
    def _legend_anchor_x_draft(self, value):
        self._workspace_state.legend_anchor_x_draft = value

    @property
    def _legend_anchor_y_draft(self):
        return self._workspace_state.legend_anchor_y_draft

    @_legend_anchor_y_draft.setter
    def _legend_anchor_y_draft(self, value):
        self._workspace_state.legend_anchor_y_draft = value

    @property
    def _preserve_partial_legend_anchor_draft(self):
        return self._workspace_state.preserve_partial_legend_anchor_draft

    @_preserve_partial_legend_anchor_draft.setter
    def _preserve_partial_legend_anchor_draft(self, value):
        self._workspace_state.preserve_partial_legend_anchor_draft = value

    @property
    def _display_dpi(self):
        return self._workspace_state.display_dpi

    @_display_dpi.setter
    def _display_dpi(self, value):
        self._workspace_state.display_dpi = value

    @property
    def _display_canvas_size(self):
        return self._workspace_state.display_canvas_size

    @_display_canvas_size.setter
    def _display_canvas_size(self, value):
        self._workspace_state.display_canvas_size = value

    @property
    def _selected_tree_kind(self):
        return self._workspace_state.selected_tree_kind

    @_selected_tree_kind.setter
    def _selected_tree_kind(self, value):
        self._workspace_state.selected_tree_kind = value

    @property
    def _selected_tree_id(self):
        return self._workspace_state.selected_tree_id

    @_selected_tree_id.setter
    def _selected_tree_id(self, value):
        self._workspace_state.selected_tree_id = value


def _safe_float(value) -> Optional[float]:
    try:
        return float(str(value).strip()) if value not in (None, "", "None") else None
    except Exception:
        return None


def _safe_float_or(value, default: float) -> float:
    parsed = _safe_float(value)
    return default if parsed is None else parsed


def _safe_int(value) -> Optional[int]:
    try:
        return int(str(value).strip()) if value not in (None, "", "None") else None
    except Exception:
        return None


def _clamp_float(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))


def _safe_int_or(value, default: int) -> int:
    try:
        if value in (None, "", "None"):
            return default
        return int(str(value).strip())
    except Exception:
        return default


def _safe_color(value) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    color = QColor(text)
    if not color.isValid():
        return None
    return color.name(QColor.NameFormat.HexRgb)


def _color_with_alpha(value: Any, alpha: Optional[float]) -> str | tuple[float, float, float, float] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        if alpha is None and len(value) >= 4:
            return (float(value[0]), float(value[1]), float(value[2]), float(value[3]))
        return (float(value[0]), float(value[1]), float(value[2]), _clamp_float(alpha if alpha is not None else 1.0, 0.0, 1.0))
    if alpha is None:
        return str(value)
    clamped_alpha = _clamp_float(alpha, 0.0, 1.0)
    color = QColor(str(value or ""))
    if not color.isValid():
        return str(value)
    color.setAlphaF(clamped_alpha)
    return (color.redF(), color.greenF(), color.blueF(), color.alphaF())


def _set_line_edit_text(widget: LineEdit, value, allow_blank: bool = False) -> None:
    widget.blockSignals(True)
    if value in (None, "", "None"):
        widget.setText("" if allow_blank else str(value or ""))
    elif isinstance(value, float):
        widget.setText(f"{value:g}")
    else:
        widget.setText(str(value))
    widget.blockSignals(False)
