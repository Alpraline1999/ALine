"""图表页面 - 共享项目树驱动的可视化。"""

from __future__ import annotations

import json
from pathlib import Path
import uuid
import warnings
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
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
    InfoBar,
    InfoBarPosition,
    LineEdit,
    ListWidget,
    PrimaryPushButton,
    PushButton,
    RoundMenu,
    SmoothScrollArea,
    TabCloseButtonDisplayMode,
    TabWidget,
    TeachingTipTailPosition,
    ToolButton,
    ToolTipFilter,
    ToolTipPosition,
    isDarkTheme,
)

from core.global_assets import global_assets, make_plot_style_asset_key, parse_plot_style_asset_key
from core.extension_api import (
    PlotExtensionContext,
    build_extension_entry,
    extension_registry,
    invoke_plot_extension_handler,
    reload_builtin_extensions,
)
from core.shortcut_manager import ShortcutBindingSet
from core.project_manager import project_manager
from models.schemas import AxisConfig, CurveStyle, CurveStyleTemplate, FigureConfig, FigureState
from ui.dialogs.export_flow import choose_picture_export_plan
from ui.dialogs.fluent_dialogs import SelectionDialog, TextInputDialog
from ui.matplotlib_fonts import configure_matplotlib_cjk, list_matplotlib_font_families
from ui.widgets.extension_panel import ExtensionConfigPanel
from ui.widgets.onboarding import OnboardingStep, PageOnboardingController
from ui.theme import WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_MIN_WIDTH, WORKBENCH_TOOL_PANEL_WIDTH, WORKBENCH_WIDE_LABEL_WIDTH, apply_button_metrics, make_hint_label, make_hsep, make_inline_label, make_section_label

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

_STYLES = [
    ("实线 —", "-", ""),
    ("虚线 - -", "--", ""),
    ("点线 ···", ":", ""),
    ("点划线 —·", "-.", ""),
    ("散点 ○", "", "o"),
    ("散点 □", "", "s"),
    ("散点 △", "", "^"),
    ("散点+线 ○—", "-", "o"),
    ("散点+线 □—", "-", "s"),
]
_STYLE_LABELS = [item[0] for item in _STYLES]
_STYLE_LINESTYLES = [item[1] for item in _STYLES]
_STYLE_MARKERS = [item[2] for item in _STYLES]

_THEME_HINTS = {
    "默认": "跟随应用配色，适合日常预览和交互调参。",
    "Nature": "紧凑、克制，适合论文主图。",
    "IEEE": "偏工程排版，适合双栏和黑白打印。",
    "ACS": "强调线宽和标记，可读性更高。",
    "简洁黑白": "强制黑白输出，适合打印和审稿。",
}

_ICON_SHOW = getattr(FIF, "VIEW", FIF.SEARCH)
_ICON_HIDE = getattr(FIF, "HIDE", FIF.CANCEL)
_ICON_EXPORT_TO_PICTURES = getattr(FIF, "IMAGE_EXPORT", FIF.PHOTO)


class ChartPage(QWidget):
    """数据可视化页面。"""

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
        self._extension_panel_visible = False
        self._extension_panel_width = 360
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
        self._plot_style_extension_options: Dict[str, dict] = {}
        self._curve_style_extension_options: Dict[str, dict] = {}
        self._plot_style_extras: Dict[str, Any] = {}
        self._display_dpi = 100.0
        self._display_canvas_size: Optional[tuple[int, int]] = None
        self._canvas_host: Optional[QScrollArea] = None
        self._selected_tree_kind: Optional[str] = None
        self._selected_tree_id: Optional[str] = None
        self._shortcut_bindings = ShortcutBindingSet()

        self._redraw_timer = QTimer(self)
        self._redraw_timer.setSingleShot(True)
        self._redraw_timer.setInterval(250)
        self._redraw_timer.timeout.connect(self._redraw_now)

        self._setup_ui()
        self._setup_shortcuts()
        self._onboarding_controller = PageOnboardingController(self, "chart", self._chart_onboarding_steps)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._onboarding_controller.schedule_auto_start()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        self._page_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._page_splitter.setHandleWidth(6)
        root.addWidget(self._page_splitter, 1)

        self._content_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._content_splitter.setHandleWidth(6)

        left_card = CardWidget(self)
        self._tool_panel = left_card
        left_card.setFixedWidth(WORKBENCH_TOOL_PANEL_WIDTH)
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(10)

        left_layout.addWidget(make_section_label("已绘图曲线", left_card))
        self._chart_list = ListWidget(left_card)
        self._chart_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._chart_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._chart_list.currentItemChanged.connect(self._on_current_changed)
        self._chart_list.customContextMenuRequested.connect(self._on_chart_list_context_menu)
        left_layout.addWidget(self._chart_list)

        self._chart_path_label = BodyLabel("路径：—", left_card)
        self._chart_path_label.setWordWrap(True)
        self._chart_path_label.setStyleSheet("color: gray; font-size: 11px;")
        left_layout.addWidget(self._chart_path_label)

        toolbar_row = QHBoxLayout()
        self._btn_clear = ToolButton(FIF.DELETE, left_card)
        self._btn_clear.setToolTip("清除当前画布中的所有曲线")
        self._btn_clear.clicked.connect(self._on_clear_chart)
        self._btn_clear.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)
        toolbar_row.addWidget(self._btn_clear)
        self._btn_remove = ToolButton(FIF.REMOVE, left_card)
        self._btn_remove.setToolTip("移除当前选中的曲线")
        self._btn_remove.clicked.connect(self._on_remove_selected)
        self._btn_remove.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)
        toolbar_row.addWidget(self._btn_remove)
        self._btn_toggle_visible = ToolButton(_ICON_HIDE, left_card)
        self._btn_toggle_visible.setToolTip("隐藏当前曲线")
        self._btn_toggle_visible.clicked.connect(self._toggle_selected_visibility)
        self._btn_toggle_visible.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)
        toolbar_row.addWidget(self._btn_toggle_visible)
        toolbar_row.addStretch()
        left_layout.addLayout(toolbar_row)

        left_layout.addWidget(make_hsep(left_card))

        self._style_tabs = TabWidget(left_card)
        self._style_tabs.tabBar.setAddButtonVisible(False)
        self._style_tabs.tabBar.setCloseButtonDisplayMode(TabCloseButtonDisplayMode.NEVER)
        self._style_tabs.addTab(self._build_curve_style_tab(left_card), "曲线样式")
        self._style_tabs.addTab(self._build_plot_style_tab(left_card), "绘图样式")
        self._style_tabs.addTab(self._build_plot_extension_tab(left_card), "绘图扩展")
        left_layout.addWidget(self._style_tabs, 1)

        left_layout.addWidget(make_hsep(left_card))
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
        left_layout.addWidget(self._plot_actions_bar)

        self._content_splitter.addWidget(left_card)

        right_card = CardWidget(self)
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(14, 14, 14, 14)
        right_layout.setSpacing(10)
        right_layout.addWidget(make_section_label("绘图预览", right_card))
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
            self._canvas.setMinimumSize(1, 1)
            canvas_host_layout.addWidget(self._canvas, 0, Qt.AlignmentFlag.AlignCenter)
            self._canvas_host.viewport().installEventFilter(self)
            right_layout.addWidget(self._canvas_host, 1)
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

        self._extension_panel = ExtensionConfigPanel("样式扩展", "应用扩展", self)
        self._extension_panel.apply_requested.connect(self._on_chart_extension_apply)
        self._extension_panel.reload_requested.connect(self._reload_chart_extensions)
        self._extension_panel.remove_requested.connect(self._on_chart_extension_remove_requested)
        self._extension_panel.selection_changed.connect(lambda _type_id: self._update_extension_remove_action())
        self._extension_panel.setMinimumWidth(self._extension_panel_width)
        self._extension_panel.setMaximumWidth(self._extension_panel_width)
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
        self.set_extension_panel_visible(self._extension_panel_visible)

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
                "曲线样式、绘图样式和绘图扩展分栏放置；叠加参考线时切到“绘图扩展”。",
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

    def supports_extension_panel_toggle(self) -> bool:
        return True

    def is_extension_panel_visible(self) -> bool:
        return bool(self._extension_panel_visible)

    def set_extension_panel_visible(self, visible: bool) -> None:
        self._extension_panel_visible = bool(visible)
        if not hasattr(self, "_extension_panel") or not hasattr(self, "_page_splitter"):
            return
        if self._extension_panel_visible:
            self._extension_panel.show()
            content_width = max(self.width() - self._extension_panel_width - 24, 760)
            self._page_splitter.setSizes([content_width, self._extension_panel_width])
            return
        self._extension_panel.hide()
        self._page_splitter.setSizes([1, 0])

    def _apply_preview_host_background(self) -> None:
        if self._canvas_host is None:
            return
        background = "#1e1e1e" if isDarkTheme() else "#ffffff"
        self._canvas_host.setStyleSheet(f"QScrollArea {{ background: {background}; border: none; }}")
        self._canvas_host.viewport().setStyleSheet(f"background: {background};")
        canvas_stage = self._canvas_host.widget()
        if canvas_stage is not None:
            canvas_stage.setStyleSheet(f"background: {background};")

    def _update_extension_remove_action(self) -> None:
        if hasattr(self, "_extension_panel"):
            self._extension_panel.set_remove_action(visible=False, enabled=False)

    def _on_chart_extension_remove_requested(self, type_id: str) -> None:
        applied = next((entry for entry in reversed(self._applied_plot_extensions) if entry.get("type") == type_id), None)
        if applied is None:
            return
        self._remove_plot_extension_instance(str(applied.get("id") or ""))

    def eventFilter(self, watched, event):
        if self._canvas_host is not None and watched is self._canvas_host.viewport() and event.type() == QEvent.Type.Resize:
            self._sync_canvas_display_geometry()
        return super().eventFilter(watched, event)

    def _install_tooltip_filters(self) -> None:
        for widget in self.findChildren(QWidget):
            if widget.toolTip():
                widget.installEventFilter(ToolTipFilter(widget, 500, ToolTipPosition.TOP))

    @staticmethod
    def _set_compact_edit_width(edit: LineEdit, width: int = 96) -> None:
        edit.setMaximumWidth(width)

    @staticmethod
    def _set_square_tool_button(button: ToolButton) -> None:
        button.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)

    @staticmethod
    def _make_style_form_label(text: str, parent: Optional[QWidget] = None, *, minimum_width: int = 0) -> BodyLabel:
        label = BodyLabel(text, parent)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        label.setMinimumWidth(max(minimum_width, label.sizeHint().width()))
        label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        return label

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

    def _build_curve_style_tab(self, parent: QWidget) -> QWidget:
        scroll, page, layout = self._create_style_tab_page(parent)

        self._curve_style_template_label = make_hint_label("当前曲线样式未绑定全局模板。", page)
        layout.addWidget(self._curve_style_template_label)

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

        line_width_row = QHBoxLayout()
        line_width_row.addWidget(self._make_style_form_label("线宽:", page))
        self._style_line_width_edit = LineEdit(page)
        self._style_line_width_edit.setPlaceholderText("1.4")
        self._style_line_width_edit.setEnabled(False)
        self._style_line_width_edit.textChanged.connect(self._on_style_metrics_changed)
        self._set_compact_edit_width(self._style_line_width_edit)
        line_width_row.addWidget(self._style_line_width_edit)
        line_width_row.addStretch()
        layout.addLayout(line_width_row)

        marker_size_row = QHBoxLayout()
        marker_size_row.addWidget(self._make_style_form_label("点大小:", page))
        self._style_marker_size_edit = LineEdit(page)
        self._style_marker_size_edit.setPlaceholderText("5.0")
        self._style_marker_size_edit.setEnabled(False)
        self._style_marker_size_edit.textChanged.connect(self._on_style_metrics_changed)
        self._set_compact_edit_width(self._style_marker_size_edit)
        marker_size_row.addWidget(self._style_marker_size_edit)
        marker_size_row.addStretch()
        layout.addLayout(marker_size_row)

        density_row = QHBoxLayout()
        density_row.addWidget(self._make_style_form_label("点间距:", page))
        self._style_density_edit = LineEdit(page)
        self._style_density_edit.setPlaceholderText("1")
        self._style_density_edit.setEnabled(False)
        self._style_density_edit.textChanged.connect(self._on_style_metrics_changed)
        self._set_compact_edit_width(self._style_density_edit)
        density_row.addWidget(self._style_density_edit)
        density_row.addStretch()
        layout.addLayout(density_row)

        layout.addStretch()
        return scroll

    def _build_plot_style_tab(self, parent: QWidget) -> QWidget:
        scroll, page, layout = self._create_style_tab_page(parent)
        self._plot_style_scroll = scroll

        self._template_summary_label = make_hint_label("当前为临时绘图样式。", page)
        layout.addWidget(self._template_summary_label)

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

        layout.addWidget(make_hsep(page))
        layout.addWidget(make_section_label("基础配置", page))

        x_row = QHBoxLayout()
        x_row.addWidget(self._make_style_form_label("X:", page))
        self._x_label_edit = LineEdit(page)
        self._x_label_edit.setPlaceholderText("X")
        self._x_label_edit.textChanged.connect(self._on_quick_config_changed)
        x_row.addWidget(self._x_label_edit)
        layout.addLayout(x_row)

        y_row = QHBoxLayout()
        y_row.addWidget(self._make_style_form_label("Y:", page))
        self._y_label_edit = LineEdit(page)
        self._y_label_edit.setPlaceholderText("Y")
        self._y_label_edit.textChanged.connect(self._on_quick_config_changed)
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
        self._x_min_edit.textChanged.connect(self._on_quick_config_changed)
        self._set_compact_edit_width(self._x_min_edit)
        x_range_row.addWidget(self._x_min_edit)
        x_range_row.addWidget(self._make_style_form_label("最大:", page))
        self._x_max_edit = LineEdit(page)
        self._x_max_edit.setPlaceholderText("自动")
        self._x_max_edit.textChanged.connect(self._on_quick_config_changed)
        self._set_compact_edit_width(self._x_max_edit)
        x_range_row.addWidget(self._x_max_edit)
        layout.addLayout(x_range_row)

        y_range_row = QHBoxLayout()
        y_range_row.addWidget(self._make_style_form_label("Y 最小:", page))
        self._y_min_edit = LineEdit(page)
        self._y_min_edit.setPlaceholderText("自动")
        self._y_min_edit.textChanged.connect(self._on_quick_config_changed)
        self._set_compact_edit_width(self._y_min_edit)
        y_range_row.addWidget(self._y_min_edit)
        y_range_row.addWidget(self._make_style_form_label("最大:", page))
        self._y_max_edit = LineEdit(page)
        self._y_max_edit.setPlaceholderText("自动")
        self._y_max_edit.textChanged.connect(self._on_quick_config_changed)
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
        self._grid_cb = CheckBox("显示网格", page)
        self._grid_cb.stateChanged.connect(self._on_quick_config_changed)
        axis_flag_row.addWidget(self._grid_cb)
        axis_flag_row.addStretch()
        layout.addLayout(axis_flag_row)

        layout.addWidget(make_hsep(page))
        layout.addWidget(make_section_label("版式与标注", page))

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
        self._font_size_edit.textChanged.connect(self._on_quick_config_changed)
        self._set_compact_edit_width(self._font_size_edit)
        font_size_row.addWidget(self._font_size_edit)
        font_size_row.addStretch()
        layout.addLayout(font_size_row)

        legend_font_row = QHBoxLayout()
        legend_font_row.addWidget(self._make_style_form_label("图例字号:", page))
        self._legend_font_size_edit = LineEdit(page)
        self._legend_font_size_edit.setPlaceholderText("8")
        self._legend_font_size_edit.textChanged.connect(self._on_quick_config_changed)
        self._set_compact_edit_width(self._legend_font_size_edit)
        legend_font_row.addWidget(self._legend_font_size_edit)
        legend_font_row.addStretch()
        layout.addLayout(legend_font_row)

        layout.addWidget(make_hsep(page))
        layout.addWidget(make_section_label("画布与默认样式", page))

        figure_width_row = QHBoxLayout()
        figure_width_row.addWidget(self._make_style_form_label("图宽:", page))
        self._figure_width_edit = LineEdit(page)
        self._figure_width_edit.setPlaceholderText("7.0")
        self._figure_width_edit.textChanged.connect(self._on_quick_config_changed)
        self._set_compact_edit_width(self._figure_width_edit)
        figure_width_row.addWidget(self._figure_width_edit)
        figure_width_row.addStretch()
        layout.addLayout(figure_width_row)

        figure_height_row = QHBoxLayout()
        figure_height_row.addWidget(self._make_style_form_label("图高:", page))
        self._figure_height_edit = LineEdit(page)
        self._figure_height_edit.setPlaceholderText("5.0")
        self._figure_height_edit.textChanged.connect(self._on_quick_config_changed)
        self._set_compact_edit_width(self._figure_height_edit)
        figure_height_row.addWidget(self._figure_height_edit)
        figure_height_row.addStretch()
        layout.addLayout(figure_height_row)

        dpi_row = QHBoxLayout()
        dpi_row.addWidget(self._make_style_form_label("DPI:", page))
        self._dpi_edit = LineEdit(page)
        self._dpi_edit.setPlaceholderText("150")
        self._dpi_edit.textChanged.connect(self._on_quick_config_changed)
        self._set_compact_edit_width(self._dpi_edit)
        dpi_row.addWidget(self._dpi_edit)
        dpi_row.addStretch()
        layout.addLayout(dpi_row)

        style_row = QHBoxLayout()
        style_row.addWidget(self._make_style_form_label("默认线宽:", page))
        self._plot_line_width_edit = LineEdit(page)
        self._plot_line_width_edit.setPlaceholderText("1.4")
        self._plot_line_width_edit.textChanged.connect(self._on_quick_config_changed)
        self._set_compact_edit_width(self._plot_line_width_edit)
        style_row.addWidget(self._plot_line_width_edit)
        style_row.addStretch()
        layout.addLayout(style_row)

        marker_row = QHBoxLayout()
        marker_row.addWidget(self._make_style_form_label("默认点大小:", page))
        self._plot_marker_size_edit = LineEdit(page)
        self._plot_marker_size_edit.setPlaceholderText("5.0")
        self._plot_marker_size_edit.textChanged.connect(self._on_quick_config_changed)
        self._set_compact_edit_width(self._plot_marker_size_edit)
        marker_row.addWidget(self._plot_marker_size_edit)
        marker_row.addStretch()
        layout.addLayout(marker_row)

        grid_style_row = QHBoxLayout()
        grid_style_row.addWidget(self._make_style_form_label("网格透明度:", page))
        self._grid_alpha_edit = LineEdit(page)
        self._grid_alpha_edit.setPlaceholderText("0.7")
        self._grid_alpha_edit.textChanged.connect(self._on_quick_config_changed)
        self._set_compact_edit_width(self._grid_alpha_edit)
        grid_style_row.addWidget(self._grid_alpha_edit)
        grid_style_row.addStretch()
        layout.addLayout(grid_style_row)

        grid_width_row = QHBoxLayout()
        grid_width_row.addWidget(self._make_style_form_label("网格线宽:", page))
        self._grid_line_width_edit = LineEdit(page)
        self._grid_line_width_edit.setPlaceholderText("0.5")
        self._grid_line_width_edit.textChanged.connect(self._on_quick_config_changed)
        self._set_compact_edit_width(self._grid_line_width_edit)
        grid_width_row.addWidget(self._grid_line_width_edit)
        grid_width_row.addStretch()
        layout.addLayout(grid_width_row)

        layout.addStretch()
        return scroll

    def _build_plot_extension_tab(self, parent: QWidget) -> QWidget:
        scroll, page, layout = self._create_style_tab_page(parent)

        extension_hint = make_hint_label("在右侧面板选择扩展，并叠加到当前图表。", page)
        layout.addWidget(extension_hint)
        extension_sub_hint = make_hint_label("适合参考线、标注或自定义绘制流程。", page)
        layout.addWidget(extension_sub_hint)

        self._plot_extension_target_hint = make_hint_label("", page)
        self._plot_extension_target_hint.setWordWrap(True)
        layout.addWidget(self._plot_extension_target_hint)
        layout.addWidget(make_hsep(page))

        applied_header = QHBoxLayout()
        applied_header.addWidget(make_section_label("已加载曲线", page))
        applied_header.addStretch()
        self._remove_selected_plot_extension_btn = PushButton("撤销选中", page)
        self._remove_selected_plot_extension_btn.clicked.connect(self._remove_selected_plot_extension)
        self._remove_selected_plot_extension_btn.setEnabled(False)
        applied_header.addWidget(self._remove_selected_plot_extension_btn)
        layout.addLayout(applied_header)

        self._plot_extension_repeat_hint = make_hint_label("同一扩展可重复加载，列表会保留目标曲线和参数摘要。", page)
        layout.addWidget(self._plot_extension_repeat_hint)

        self._plot_extension_applied_list = ListWidget(page)
        self._plot_extension_applied_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._plot_extension_applied_list.currentItemChanged.connect(self._on_plot_extension_instance_selection_changed)
        layout.addWidget(self._plot_extension_applied_list, 1)
        self._refresh_plot_extension_list()
        return scroll

    def on_tree_node_selected(self, kind: str, node_id: str) -> None:
        self._selected_tree_kind = kind
        self._selected_tree_id = node_id

    def on_tree_node_activated(self, kind: str, node_id: str) -> None:
        if kind == "global_curve_style_template":
            self.load_curve_style_template(node_id)
            return
        if kind in ("global_plot_style", "global_plot_theme"):
            self.load_plot_style(node_id)
            return
        if kind.endswith("_to_chart"):
            kind = kind[:-9]
        series_list = project_manager.get_all_series_from_node(kind, node_id)
        if not series_list:
            return
        self._add_series_batch(series_list, source="tree")

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

    def _curve_tree_path_label(self, curve: Optional[dict]) -> str:
        if curve is None:
            return "—"
        obj_id = str(curve.get("obj_id") or "")
        if obj_id:
            path = project_manager.format_series_origin_path_label(obj_id, separator="/", omit_root_group=True)
            if path:
                return path
        return "未关联项目树"

    def _update_selected_curve_path_label(self, curve: Optional[dict]) -> None:
        path = self._curve_tree_path_label(curve)
        self._chart_path_label.setText(f"路径：{path}")
        self._chart_path_label.setToolTip(path if path not in {"—", "未关联项目树"} else "")

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
        for extension in extension_registry.list_plot_style():
            label = self._unique_style_label(f"扩展 · {extension.name}", used_labels, "扩展")
            choices.append((label, make_plot_style_asset_key("extension", extension.type)))
        return choices

    def _plot_style_extension_entries(self) -> List[dict]:
        entries: List[dict] = []
        for extension in extension_registry.list_plot_style():
            entry = build_extension_entry(extension)
            entry["label"] = f"样式扩展 · {extension.name}"
            entries.append(entry)
        return entries

    def _plot_extension_entries(self) -> List[dict]:
        entries: List[dict] = []
        for extension in extension_registry.list_plot():
            entry = build_extension_entry(extension)
            entry["label"] = f"绘图扩展 · {extension.name}"
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
        return {
            "id": self._next_plot_extension_instance_id(),
            "type": type_id,
            "options": dict(options),
            "curve_identity": self._curve_identity(target_curve) if target_curve is not None else None,
            "curve_name": target_curve.get("name") if target_curve is not None else None,
            "curve_display_name": self._curve_display_name(target_curve) if target_curve is not None else "",
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
            item.setToolTip(json.dumps(dict(entry.get("options") or {}), ensure_ascii=False, indent=2))
            self._plot_extension_applied_list.addItem(item)
            if entry.get("id") == target_instance_id:
                target_row = index
        if self._plot_extension_applied_list.count() > 0:
            if target_row < 0:
                target_row = 0
            self._plot_extension_applied_list.setCurrentRow(target_row)
        self._plot_extension_applied_list.blockSignals(False)
        self._on_plot_extension_instance_selection_changed(self._plot_extension_applied_list.currentItem(), None)

    def _on_plot_extension_instance_selection_changed(self, current, _previous) -> None:
        has_selection = current is not None
        if hasattr(self, "_remove_selected_plot_extension_btn"):
            self._remove_selected_plot_extension_btn.setEnabled(has_selection)
        if not has_selection or not hasattr(self, "_extension_panel"):
            return
        applied = self._selected_plot_extension_instance()
        if applied is None:
            return
        type_id = str(applied.get("type") or "")
        target_index = next(
            (index for index, entry in enumerate(self._extension_panel._entries) if entry.get("type") == type_id),
            -1,
        )
        if target_index >= 0:
            self._extension_panel._selector.setCurrentIndex(target_index)
        self._extension_panel._editor.setPlainText(json.dumps(dict(applied.get("options") or {}), ensure_ascii=False, indent=2))

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

    def _curve_style_extension_entries(self) -> List[dict]:
        return [build_extension_entry(extension) for extension in extension_registry.list_curve_style()]

    def _refresh_style_extension_panel(self, _index: Optional[int] = None) -> None:
        current_tab = self._style_tabs.currentIndex()
        if current_tab == 0:
            selected_curve = self._selected_curve()
            target = selected_curve["name"] if selected_curve is not None else "未选中曲线"
            available_types = {entry["type"] for entry in self._curve_style_extension_entries()}
            panel_current_type = self._extension_panel.current_type() if hasattr(self, "_extension_panel") else None
            current_type = None
            if panel_current_type in available_types:
                current_type = panel_current_type
            elif self._active_curve_style_ref and self._active_curve_style_ref.startswith("curve_extension:"):
                current_type = parse_plot_style_asset_key(self._active_curve_style_ref)[1]
            self._extension_panel.set_panel_title("曲线样式扩展")
            self._extension_panel.set_action_text("应用扩展")
            self._extension_panel.set_context("图表样式", target)
            self._extension_panel.set_status_context("curve_style", "曲线样式扩展")
            self._extension_panel.set_entries(
                self._curve_style_extension_entries(),
                saved_options=self._curve_style_extension_options,
                current_type=current_type,
            )
            self._update_extension_remove_action()
            return
        if current_tab == 1:
            plot_style_entries = self._plot_style_extension_entries()
            available_types = {entry["type"] for entry in plot_style_entries}
            panel_current_type = self._extension_panel.current_type() if hasattr(self, "_extension_panel") else None
            current_type = None
            if panel_current_type in available_types:
                current_type = panel_current_type
            elif self._applied_plot_style_ref and self._applied_plot_style_ref.startswith("extension:"):
                current_type = parse_plot_style_asset_key(self._applied_plot_style_ref)[1]
            self._extension_panel.set_panel_title("绘图样式扩展")
            self._extension_panel.set_action_text("应用扩展")
            self._extension_panel.set_context("图表样式", self._figure_state.theme or "绘图样式")
            self._extension_panel.set_status_context("plot_style", "绘图样式扩展")
            self._extension_panel.set_entries(
                plot_style_entries,
                saved_options=self._plot_style_extension_options,
                current_type=current_type,
            )
            self._update_extension_remove_action()
            return

        plot_entries = self._plot_extension_entries()
        available_types = {entry["type"] for entry in plot_entries}
        panel_current_type = self._extension_panel.current_type() if hasattr(self, "_extension_panel") else None
        current_type = None
        if panel_current_type in available_types:
            current_type = panel_current_type
        else:
            current_type = next(
                (str(entry.get("type")) for entry in reversed(self._applied_plot_extensions) if entry.get("type") in available_types),
                None,
            ) or next((type_id for type_id in self._plot_extension_options if type_id in available_types), None)
        self._extension_panel.set_panel_title("绘图扩展")
        self._extension_panel.set_action_text("应用扩展")
        self._extension_panel.set_context("图表样式", self._figure_state.theme or "绘图样式")
        self._extension_panel.set_status_context("plot", "绘图扩展")
        self._extension_panel.set_entries(
            plot_entries,
            saved_options=self._plot_extension_options,
            current_type=current_type,
        )
        self._update_extension_remove_action()
        self._refresh_plot_extension_list()

    def _on_chart_extension_apply(self, type_id: str, options: Dict[str, Any]) -> None:
        current_tab = self._style_tabs.currentIndex()
        if current_tab == 0:
            self._curve_style_extension_options[type_id] = dict(options)
            self._apply_curve_style_extension(type_id)
            return
        if current_tab == 2:
            self._plot_extension_options[type_id] = dict(options)
            self._apply_plot_extension(type_id)
            return
        self._plot_style_extension_options[type_id] = dict(options)
        self._apply_plot_style_extension(type_id)

    def _reload_chart_extensions(self) -> None:
        report = reload_builtin_extensions()
        plot_types = {extension.type for extension in extension_registry.list_plot()}
        plot_style_types = {extension.type for extension in extension_registry.list_plot_style()}
        curve_style_types = {extension.type for extension in extension_registry.list_curve_style()}
        self._plot_extension_options = {key: value for key, value in self._plot_extension_options.items() if key in plot_types}
        self._applied_plot_extensions = [entry for entry in self._applied_plot_extensions if entry.get("type") in plot_types]
        self._plot_style_extension_options = {key: value for key, value in self._plot_style_extension_options.items() if key in plot_style_types}
        self._curve_style_extension_options = {key: value for key, value in self._curve_style_extension_options.items() if key in curve_style_types}
        self._refresh_curve_style_template_combo()
        self._refresh_template_combo(self._applied_plot_style_ref)
        self._refresh_style_extension_panel()
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
        elif style_type == "extension":
            extension = extension_registry.get_plot_style(asset_id)
            if extension is not None:
                self._template_summary_label.setText(
                    f"{pending_message}当前使用扩展绘图样式: {extension.name}".strip()
                )
                self._btn_update_template.setEnabled(False)
                return
        else:
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
        if style_type == "extension":
            self._apply_plot_style_extension(asset_id)
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
        self._plot_style_extras = {}
        self._apply_figure_state(state)
        self._redraw_now()
        self._refresh_style_extension_panel()

    def _apply_plot_style_extension(self, type_id: str) -> None:
        extension = extension_registry.get_plot_style(type_id)
        if extension is None:
            return
        current_state = self._current_plot_style_payload()
        options = dict(self._plot_style_extension_options.get(type_id, extension.default_options))
        state_patch = extension.handler(dict(current_state), options)
        if not isinstance(state_patch, dict):
            return
        merged_state = dict(current_state)
        merged_state.update(state_patch)
        merged_state.setdefault("theme", extension.name)
        self._active_template_node_id = None
        self._current_plot_theme_id = None
        self._applied_plot_style_ref = make_plot_style_asset_key("extension", type_id)
        self._apply_plot_style_payload(merged_state)
        self._refresh_template_combo(self._applied_plot_style_ref)
        self._refresh_style_extension_panel()
        self._redraw_now()

    def _apply_plot_extension(self, type_id: str) -> None:
        extension = extension_registry.get_plot(type_id)
        if extension is None:
            return
        options = dict(self._plot_extension_options.get(type_id, extension.default_options))
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
        self._plot_style_extras = {}
        self._apply_figure_state(state)
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
        for extension in extension_registry.list_curve_style():
            self._curve_style_template_combo.addItem(f"扩展 · {extension.name}")
            self._curve_style_template_ids.append(make_plot_style_asset_key("curve_extension", extension.type))
        target_id = self._active_curve_style_ref
        if target_id in self._curve_style_template_ids:
            self._curve_style_template_combo.setCurrentIndex(self._curve_style_template_ids.index(target_id))
        else:
            self._curve_style_template_combo.setCurrentIndex(0)
        self._curve_style_template_combo.blockSignals(False)
        self._update_curve_style_template_summary()
        self._refresh_style_extension_panel()

    def _update_curve_style_template_summary(self) -> None:
        if not self._active_curve_style_ref:
            self._curve_style_template_label.setText("当前曲线样式未绑定全局模板。")
            self._btn_update_curve_style_template.setEnabled(False)
            return
        if self._active_curve_style_ref.startswith("curve_extension:"):
            extension = extension_registry.get_curve_style(parse_plot_style_asset_key(self._active_curve_style_ref)[1])
            if extension is None:
                self._active_curve_style_ref = None
                self._curve_style_template_label.setText("当前曲线样式未绑定全局模板。")
                self._btn_update_curve_style_template.setEnabled(False)
                self._refresh_style_extension_panel()
                return
            self._curve_style_template_label.setText(f"当前扩展样式: {extension.name}")
            self._btn_update_curve_style_template.setEnabled(False)
            self._refresh_style_extension_panel()
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
            if style_ref.startswith("curve_extension:"):
                self._active_curve_style_template_id = None
            else:
                self._active_curve_style_template_id = style_ref
            self._update_curve_style_template_summary()

    def _load_selected_curve_style_template(self) -> None:
        style_ref = self._selected_curve_style_template_id()
        if not style_ref:
            InfoBar.warning("提示", "请先选择一个曲线样式", parent=self, position=InfoBarPosition.TOP)
            return
        if style_ref.startswith("curve_extension:"):
            self._apply_curve_style_extension(parse_plot_style_asset_key(style_ref)[1])
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

    def _apply_curve_style_extension(self, type_id: str) -> None:
        extension = extension_registry.get_curve_style(type_id)
        if extension is None:
            return
        curve = self._selected_curve()
        if curve is None:
            InfoBar.warning("提示", "请先选中一条曲线再应用扩展样式", parent=self, position=InfoBarPosition.TOP)
            return
        current_style = self._current_curve_style(curve)
        if current_style is None:
            return
        options = dict(self._curve_style_extension_options.get(type_id, extension.default_options))
        current_payload = self._current_curve_style_payload(curve)
        style_patch = extension.handler(dict(current_payload), options)
        if not isinstance(style_patch, dict):
            return
        merged_style = dict(current_payload)
        merged_style.update(style_patch)
        self._apply_curve_style_payload(self._curve_key(curve), merged_style)
        self._active_curve_style_template_id = None
        self._active_curve_style_ref = make_plot_style_asset_key("curve_extension", type_id)
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

    def _apply_curve_style_payload(self, curve_key: str, payload: Dict[str, Any]) -> None:
        style_dict = self._curve_styles.setdefault(curve_key, {})
        style_dict.update({key: value for key, value in payload.items() if key != "visible"})
        for curve in self._chart_series:
            if self._curve_key(curve) == curve_key:
                if "visible" in payload:
                    curve["visible"] = bool(payload.get("visible", True))
                break
        self._refresh_chart_list()
        selected_curve = self._selected_curve()
        if selected_curve and self._curve_key(selected_curve) == curve_key:
            self._set_style_enabled(True, selected_curve)

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
        payload = self._get_current_config()
        payload.update(cfg)
        self._applied_plot_style_ref = (
            make_plot_style_asset_key("template", self._active_template_node_id)
            if self._active_template_node_id
            else None
        )
        self._apply_plot_style_payload(payload)

    def _current_plot_style_payload(self) -> Dict[str, Any]:
        payload = self._sync_state_from_controls().model_dump()
        payload.update(self._plot_style_extras)
        return payload

    def _apply_plot_style_payload(self, payload: Dict[str, Any]) -> None:
        figure_fields = set(FigureState.model_fields.keys())
        state_payload = {key: value for key, value in payload.items() if key in figure_fields}
        self._plot_style_extras = {key: value for key, value in payload.items() if key not in figure_fields}
        self._apply_figure_state(FigureState(**state_payload))

    def _apply_figure_state(self, state: FigureState) -> None:
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
        _set_line_edit_text(self._grid_alpha_edit, state.grid_alpha)
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
            grid_alpha=_clamp_float(_safe_float_or(self._grid_alpha_edit.text(), self._figure_state.grid_alpha), 0.0, 1.0),
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
        self._sync_state_from_controls()
        self._theme_hint_label.setText(_THEME_HINTS.get(self._figure_state.theme, ""))
        self._redraw()

    def _selected_curve(self) -> Optional[dict]:
        return self._curve_from_item(self._chart_list.currentItem())

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
        menu.exec(self._chart_list.mapToGlobal(pos))

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
            display_name = self._curve_display_name(curve)
            label = display_name if curve.get("visible", True) else f"[隐藏] {display_name}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, self._curve_key(curve))
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
            return
        visible = bool(curve.get("visible", True))
        self._btn_toggle_visible.setEnabled(True)
        self._btn_toggle_visible.setIcon((_ICON_HIDE if visible else _ICON_SHOW).icon())
        self._btn_toggle_visible.setToolTip("隐藏当前曲线" if visible else "显示当前曲线")

    def _on_clear_chart(self) -> None:
        self._chart_series.clear()
        self._curve_styles.clear()
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
        if self._style_target == target_key:
            self._style_target = None
        self._refresh_chart_list()
        self._redraw_now()

    def _toggle_selected_visibility(self) -> None:
        curve = self._selected_curve()
        if curve is None:
            return
        curve["visible"] = not bool(curve.get("visible", True))
        self._refresh_chart_list()
        self._redraw_now()

    def _redraw(self) -> None:
        self._redraw_timer.start()

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

    def _redraw_now(self) -> None:
        if not HAS_MATPLOTLIB or self._figure is None or self._canvas is None:
            return

        self._redraw_timer.stop()
        state = self._sync_state_from_controls()
        self._sync_canvas_display_geometry(state)
        self._figure.clear()
        axis = self._figure.add_subplot(111)
        theme = self._resolve_plot_theme()

        dark = isDarkTheme()
        self._apply_preview_host_background()
        if theme is None or theme.canvas_mode == "app":
            bg = theme.background_color if theme and theme.background_color else ("#1e1e1e" if dark else "#ffffff")
            fg = theme.foreground_color if theme and theme.foreground_color else ("#cccccc" if dark else "#222222")
            grid_color = theme.grid_color if theme and theme.grid_color else ("#444444" if dark else "#dddddd")
        elif theme.canvas_mode == "dark":
            bg = theme.background_color or "#1e1e1e"
            fg = theme.foreground_color or "#e6e6e6"
            grid_color = theme.grid_color or "#454545"
        else:
            bg = theme.background_color or "#ffffff"
            fg = theme.foreground_color or "#222222"
            grid_color = theme.grid_color or "#dddddd"

        figure_facecolor = self._plot_style_extras.get("figure_facecolor")
        axes_facecolor = self._plot_style_extras.get("axes_facecolor")
        visible_series = [curve for curve in self._chart_series if curve.get("visible", True)]
        selected_curve = self._selected_curve()
        bw_colors = ["#000000", "#444444", "#888888", "#aaaaaa"]
        bw_index = 0
        default_line_kwargs = dict(self._plot_style_extras.get("line_defaults", {}) or {})
        errorbar_kwargs = dict(self._plot_style_extras.get("errorbar_kwargs", {}) or {})
        reserved_curve_keys = {
            "color", "linestyle", "marker", "linewidth", "marker_size", "alpha", "markevery", "dash_scale",
        }
        plotted_series: List[dict] = []

        plot_context = PlotExtensionContext(
            figure=self._figure,
            canvas=self._canvas,
            axis=axis,
            axes=[axis],
            visible_series=[dict(curve) for curve in visible_series],
            plotted_series=plotted_series,
            selected_series=(dict(selected_curve) if selected_curve is not None else None),
            selected_series_identity=(self._curve_identity(selected_curve) if selected_curve is not None else None),
            figure_state=self._current_plot_style_payload(),
            plot_style_extras=dict(self._plot_style_extras),
            theme_colors={"background": bg, "foreground": fg, "grid": grid_color},
        )

        for applied in list(self._applied_plot_extensions):
            type_id = str(applied.get("type") or "")
            extension = extension_registry.get_plot(type_id)
            if extension is None:
                continue
            target_curve = self._resolve_plot_extension_curve(applied.get("curve_identity"))
            plot_context.selected_series = dict(target_curve) if target_curve is not None else None
            plot_context.selected_series_identity = self._curve_identity(target_curve) if target_curve is not None else applied.get("curve_identity")
            try:
                plot_context.phase = "before_plot"
                invoke_plot_extension_handler(extension.handler, plot_context, dict(applied.get("options") or {}))
            except Exception:
                continue
            plot_context.refresh_axes()

        axis = plot_context.axis
        if axis is None:
            axis = self._figure.add_subplot(111)
            plot_context.set_active_axis(axis)

        self._figure.patch.set_facecolor(figure_facecolor or bg)
        if axis is not None and not plot_context.skip_default_formatting:
            axis.set_facecolor(axes_facecolor or bg)
            for spine in axis.spines.values():
                spine.set_edgecolor(fg)

            grid_kwargs = {
                "color": grid_color,
                "linestyle": "--",
                "linewidth": state.grid_line_width,
                "alpha": state.grid_alpha,
            }
            grid_kwargs.update(dict(self._plot_style_extras.get("grid_kwargs", {}) or {}))
            axis.grid(state.grid, **grid_kwargs)

        if not plot_context.skip_default_plot and axis is not None:
            for curve in visible_series:
                display_name = self._curve_display_name(curve)
                style_overrides = self._curve_styles.get(self._curve_key(curve), {})
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
                plotted_series.append({**curve, "display_name": display_name, "style": dict(style_overrides)})
                if state.show_errbar and y_err and len(y_err) == len(x_values):
                    axis.errorbar(x_values, y_values, yerr=y_err, capsize=3, **errorbar_kwargs, **plot_kwargs)
                else:
                    axis.plot(x_values, y_values, **plot_kwargs)

        for applied in list(self._applied_plot_extensions):
            type_id = str(applied.get("type") or "")
            extension = extension_registry.get_plot(type_id)
            if extension is None:
                continue
            target_curve = self._resolve_plot_extension_curve(applied.get("curve_identity"))
            try:
                plot_context.phase = "after_plot"
                plot_context.axis = axis
                plot_context.selected_series = dict(target_curve) if target_curve is not None else None
                plot_context.selected_series_identity = self._curve_identity(target_curve) if target_curve is not None else applied.get("curve_identity")
                invoke_plot_extension_handler(extension.handler, plot_context, dict(applied.get("options") or {}))
            except Exception:
                continue
            plot_context.refresh_axes()

        axis = plot_context.axis or axis

        legend = None
        if visible_series and not plot_context.skip_default_plot and axis is not None and not plot_context.skip_default_formatting:
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
            legend_kwargs.update(dict(self._plot_style_extras.get("legend_kwargs", {}) or {}))
            legend = axis.legend(
                **legend_kwargs,
            )

        if axis is not None and not plot_context.skip_default_formatting:
            axis.set_xlabel(state.x_label or "X")
            axis.set_ylabel(state.y_label or "Y")
            if state.x_min is not None or state.x_max is not None:
                axis.set_xlim(left=state.x_min, right=state.x_max)
            if state.y_min is not None or state.y_max is not None:
                axis.set_ylim(bottom=state.y_min, top=state.y_max)
            if state.x_log:
                axis.set_xscale("log")
            if state.y_log:
                axis.set_yscale("log")

            axis_kwargs = dict(self._plot_style_extras.get("axis_kwargs", {}) or {})
            if axis_kwargs:
                axis.set(**axis_kwargs)

            self._apply_axis_text_style(axis, state, fg)
            tick_params = dict(self._plot_style_extras.get("tick_params", {}) or {})
            if tick_params:
                axis.tick_params(**tick_params)
            if legend is not None:
                for text in legend.get_texts():
                    self._apply_text_style(text, font_family=state.font_family, font_size=state.legend_font_size, color=fg)
                self._apply_text_style(legend.get_title(), font_family=state.font_family, font_size=state.legend_font_size, color=fg)

        if not plot_context.skip_default_layout:
            self._apply_figure_layout(state)
            subplot_adjust = self._plot_style_extras.get("subplot_adjust")
            if isinstance(subplot_adjust, dict) and subplot_adjust:
                self._figure.subplots_adjust(**subplot_adjust)
        self._canvas.draw()
        self._canvas.updateGeometry()

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
        self._style_marker_size_edit.setEnabled(enabled)
        self._style_density_edit.setEnabled(enabled)
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
            self._style_marker_size_edit.blockSignals(True)
            self._style_marker_size_edit.setText(f"{style.marker_size:g}")
            self._style_marker_size_edit.blockSignals(False)
            self._style_density_edit.blockSignals(True)
            self._style_density_edit.setText(str(style.markevery))
            self._style_density_edit.blockSignals(False)
        else:
            self._style_target = None
            self._style_target_label.setText("当前选中：未选中")
            self._style_target_label.setToolTip("")
            self._update_color_btn("#888888")
            self._style_line_width_edit.clear()
            self._style_marker_size_edit.clear()
            self._style_density_edit.clear()

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
        self._curve_styles.setdefault(self._style_target, {})["color"] = color_obj.name(QColor.NameFormat.HexRgb)
        self._redraw_now()

    def _on_style_reset_color(self) -> None:
        if not self._style_target:
            return
        self._curve_styles.get(self._style_target, {}).pop("color", None)
        for curve in self._chart_series:
            if self._curve_key(curve) == self._style_target:
                self._update_color_btn(curve.get("color") or "#888888")
                break
        self._redraw_now()

    def _on_style_line_changed(self, idx: int) -> None:
        if not self._style_target:
            return
        style = self._curve_styles.setdefault(self._style_target, {})
        style["linestyle"] = _STYLE_LINESTYLES[idx]
        style["marker"] = _STYLE_MARKERS[idx]
        self._redraw_now()

    def _on_style_metrics_changed(self) -> None:
        if not self._style_target:
            return
        style = self._curve_styles.setdefault(self._style_target, {})
        style["linewidth"] = max(0.1, _safe_float_or(self._style_line_width_edit.text(), self._figure_state.line_width))
        style["marker_size"] = max(0.1, _safe_float_or(self._style_marker_size_edit.text(), self._figure_state.marker_size))
        density = max(1, _safe_int_or(self._style_density_edit.text(), 1))
        style["markevery"] = density
        style["dash_scale"] = float(density)
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
        node = project_manager.add_picture(file_path, name=Path(file_path).name, parent_id=target_folder_id)
        if node is None:
            InfoBar.error("导出失败", "图片记录写入项目失败", parent=self, position=InfoBarPosition.TOP)
            return
        self.project_modified.emit()
        InfoBar.success("已导出到图片集", Path(file_path).name, parent=self, position=InfoBarPosition.TOP)

    def update_theme(self) -> None:
        self._redraw_now()


def _safe_float(value) -> Optional[float]:
    try:
        return float(str(value).strip()) if value not in (None, "", "None") else None
    except Exception:
        return None


def _safe_float_or(value, default: float) -> float:
    parsed = _safe_float(value)
    return default if parsed is None else parsed


def _clamp_float(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))


def _safe_int_or(value, default: int) -> int:
    try:
        if value in (None, "", "None"):
            return default
        return int(str(value).strip())
    except Exception:
        return default


def _set_line_edit_text(widget: LineEdit, value, allow_blank: bool = False) -> None:
    widget.blockSignals(True)
    if value in (None, "", "None"):
        widget.setText("" if allow_blank else str(value or ""))
    elif isinstance(value, float):
        widget.setText(f"{value:g}")
    else:
        widget.setText(str(value))
    widget.blockSignals(False)

