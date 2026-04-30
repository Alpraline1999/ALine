"""数据处理页

三列布局：左侧数据选择 | 中间操作链 | 右侧效果预览
支持非破坏性操作管道，结果可另存为新数据系列或数据文件。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QItemSelectionModel, Qt, QTimer, Signal
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QListWidgetItem, QSizePolicy, QSplitter, QStackedWidget, QVBoxLayout, QWidget, QTreeWidgetItem
from qfluentwidgets import (
    BodyLabel, CaptionLabel, ComboBox, FluentIcon as FIF,
    CardWidget,
    InfoBar, InfoBarPosition, LineEdit,
    PrimaryPushButton, PushButton, ToolButton,
    TeachingTipTailPosition,
    TreeWidget, ListWidget, ToolTipFilter, ToolTipPosition,
)

from core.extension_api import build_extension_entry, extension_lines_number, extension_registry, normalize_extension_lines_list
from core.extension_loader import ensure_configured_extensions_loaded, reload_configured_extensions
from core.shortcut_manager import ShortcutBindingSet
from app.workspaces.process_workspace import ProcessWorkspaceController, ProcessWorkspaceState
from ui.theme import (
    WORKBENCH_BUTTON_HEIGHT,
    WORKBENCH_BUTTON_MIN_WIDTH,
    WORKBENCH_TOOL_PANEL_WIDTH,
    apply_button_metrics,
    preview_canvas_background_color,
    preview_canvas_foreground_color,
    preview_canvas_grid_color,
    secondary_color,
    make_section_label,
    make_hsep,
)
from ui.dialogs.fluent_dialogs import TextInputDialog
from ui.dialogs.export_flow import choose_data_export_batch_plan, choose_data_export_plan
from ui.widgets.extension_panel import ExtensionConfigPanel
from ui.widgets.extension_options_form import ExtensionOptionsForm
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
from ui.widgets.onboarding import OnboardingStep, PageOnboardingController
from ui.page_view_state import ProcessPageViewState
from core.global_assets import global_assets
from core.project_manager import project_manager
from models.schemas import DataFile, DataSeries, SavedPipeline
from processing.data_engine import apply_pipeline_to_lines
from processing.pipeline_extension import build_pipeline_extension_definition
from .page_shell_helpers import ExtensionPanelShellMixin, sync_vertical_splitter_sizes

try:
    import matplotlib
    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    from qfluentwidgets import isDarkTheme
    _HAS_MPL = True
except Exception:
    _HAS_MPL = False


# ── 操作定义 ─────────────────────────────────────────────────

_PREFERRED_PROCESSING_ORDER = (
    "crop",
    "smooth",
    "normalize",
    "resample",
    "pairwise_compute",
    "fft",
    "derivative",
    "integral",
    "transform",
    "filter",
)


def _install_fluent_tip(widget, text: str, position=ToolTipPosition.RIGHT) -> None:
    widget.setToolTip(text)
    widget.installEventFilter(ToolTipFilter(widget, 300, position))


def _downsample(xs: list, ys: list, max_pts: int = 2000):
    """等步幅降采样，保证渲染点数不超过 max_pts。"""
    n = len(xs)
    if n <= max_pts:
        return xs, ys
    stride = n // max_pts
    return xs[::stride], ys[::stride]


class ProcessPage(ExtensionPanelShellMixin, QWidget):
    """数据处理页：非破坏性操作管道。"""

    extensions_reloaded = Signal()
    project_modified = Signal()  # 操作链保存等操作导致项目修改时发出
    assets_modified = Signal()   # 全局 Pipeline 模板变更时发出

    @property
    def _selected_inputs(self):
        return self._workspace_state.selected_inputs

    @_selected_inputs.setter
    def _selected_inputs(self, value):
        self._workspace_state.selected_inputs = value

    @property
    def _src_series_batch(self):
        return self._workspace_state.src_series_batch

    @_src_series_batch.setter
    def _src_series_batch(self, value):
        self._workspace_state.src_series_batch = value

    @property
    def _out_series_batch(self):
        return self._workspace_state.out_series_batch

    @_out_series_batch.setter
    def _out_series_batch(self, value):
        self._workspace_state.out_series_batch = value

    @property
    def _pipeline_warnings(self):
        return self._workspace_state.pipeline_warnings

    @_pipeline_warnings.setter
    def _pipeline_warnings(self, value):
        self._workspace_state.pipeline_warnings = value

    @property
    def _selected_src_id(self):
        return self._workspace_state.selected_src_id

    @_selected_src_id.setter
    def _selected_src_id(self, value):
        self._workspace_state.selected_src_id = value

    @property
    def _selected_source_kind(self):
        return self._workspace_state.selected_source_kind

    @_selected_source_kind.setter
    def _selected_source_kind(self, value):
        self._workspace_state.selected_source_kind = value

    @property
    def _selected_source_node_id(self):
        return self._workspace_state.selected_source_node_id

    @_selected_source_node_id.setter
    def _selected_source_node_id(self, value):
        self._workspace_state.selected_source_node_id = value

    @property
    def _current_pipeline_id(self):
        return self._workspace_state.current_pipeline_id

    @_current_pipeline_id.setter
    def _current_pipeline_id(self, value):
        self._workspace_state.current_pipeline_id = value

    @property
    def _save_target_ids(self):
        return self._workspace_state.save_target_ids

    @_save_target_ids.setter
    def _save_target_ids(self, value):
        self._workspace_state.save_target_ids = value

    def __init__(self, parent=None):
        super().__init__(parent)
        ensure_configured_extensions_loaded()
        self._workspace_state = ProcessWorkspaceState()
        self._workspace_controller = ProcessWorkspaceController(self._workspace_state)
        self._view_state = ProcessPageViewState()
        self._src_xs: List[float] = []
        self._src_ys: List[float] = []
        self._out_xs: List[float] = []
        self._out_ys: List[float] = []
        self._selected_inputs = []
        self._src_series_batch = []
        self._out_series_batch = []
        self._pipeline_warnings = []
        self._ops: List[Dict[str, Any]] = []
        self._param_widgets: List[_ParamWidget] = []
        self._pipeline_selected_node_ids: List[str] = []
        self._processing_op_labels: List[str] = []
        self._processing_op_types: List[str] = []
        self._processing_label_map: Dict[str, str] = {}
        self._processing_op_hints: Dict[str, str] = {}
        self._processing_extension_options: Dict[str, Dict[str, Any]] = {}
        self._preview_nav_toolbar = None
        self._selected_src_id = None
        self._selected_source_kind = None
        self._selected_source_node_id = None
        self._current_pipeline_id = None
        self._pipeline_template_ids: List[str] = []
        self._save_target_ids = []
        # 防抖定时器：参数变更时防止每次按键都触发管道计算
        self._run_timer = QTimer(self)
        self._run_timer.setSingleShot(True)
        self._run_timer.setInterval(300)
        self._run_timer.timeout.connect(self._run_pipeline_now)
        self._shortcut_bindings = ShortcutBindingSet()
        self._setup_ui()
        self._setup_shortcuts()
        self._refresh_tree()
        self._click_away_focus_commit = install_click_away_focus_commit(self)
        self._onboarding_controller = PageOnboardingController(self, "process", self._process_onboarding_steps)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._sync_selected_input_splitter_sizes)
        self._onboarding_controller.schedule_auto_start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._view_state.selected_input_splitter_user_resized:
            QTimer.singleShot(0, self._sync_selected_input_splitter_sizes)

    def _sync_selected_input_splitter_sizes(self) -> None:
        sync_vertical_splitter_sizes(
            getattr(self, "_selected_input_splitter", None),
            user_resized=self._view_state.selected_input_splitter_user_resized,
            upper_ratio=0.4,
        )

    def _on_selected_input_splitter_moved(self, _pos: int, _index: int) -> None:
        self._view_state.selected_input_splitter_user_resized = True

    # ─────────────────────────────────────────────────────────
    # UI 构建
    # ─────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        self._page_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._page_splitter.setHandleWidth(4)
        root.addWidget(self._page_splitter, 1)

        self._content_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._content_splitter.setHandleWidth(4)
        self._content_splitter.addWidget(self._build_middle())
        self._content_splitter.addWidget(self._build_right())
        self._content_splitter.setSizes([360, 620])
        self._page_splitter.addWidget(self._content_splitter)

        self._extension_panel = ExtensionConfigPanel("处理扩展", "应用扩展", self, mode="help_only", framed=True)
        self._extension_panel.set_context("数据处理", "当前操作链")
        self._extension_panel.set_status_context("processing", "处理扩展")
        self._extension_panel.apply_requested.connect(self._on_processing_extension_apply)
        self._extension_panel.configs_changed.connect(self.assets_modified.emit)
        self._extension_panel.reload_requested.connect(self._reload_processing_extensions)
        self._extension_panel.setMinimumWidth(self._view_state.extension_panel_width)
        self._extension_panel.setMaximumWidth(self._view_state.extension_panel_width)
        self._page_splitter.addWidget(self._extension_panel)
        self._page_splitter.setStretchFactor(0, 1)
        self._page_splitter.setStretchFactor(1, 0)
        self._refresh_processing_extensions()
        self.set_extension_panel_visible(self._view_state.extension_panel_visible)
        self._apply_preview_host_background()

    def _setup_shortcuts(self) -> None:
        context = Qt.ShortcutContext.WidgetWithChildrenShortcut
        self._shortcut_bindings.bind("process_add_op", self, self._add_op, context=context)
        self._shortcut_bindings.bind("process_clear_ops", self, self._clear_ops, context=context)
        self._shortcut_bindings.bind("process_remove_op", self, self._remove_op, context=context)
        self._shortcut_bindings.bind("process_move_op_up", self, self._move_op_up, context=context)
        self._shortcut_bindings.bind("process_move_op_down", self, self._move_op_down, context=context)
        self._shortcut_bindings.bind("process_run_pipeline", self, self._run_pipeline_now, context=context)

    def apply_shortcuts(self) -> None:
        self._shortcut_bindings.apply()

    def start_onboarding(self, force: bool = False) -> None:
        self._onboarding_controller.start(force=force)

    def _process_onboarding_steps(self) -> list[OnboardingStep]:
        return [
            OnboardingStep(
                lambda: self._current_input_label,
                TeachingTipTailPosition.BOTTOM,
                "先选输入",
                "从共享树双击数据后，这里会同步已选择列表和当前处理范围。",
            ),
            OnboardingStep(
                lambda: self._pipeline_lines_button,
                TeachingTipTailPosition.BOTTOM,
                "多曲线工具统一从这里选线",
                "单曲线工具会处理列表中当前选中的项；双/多曲线工具则按顶部选择曲线的顺序执行。",
            ),
            OnboardingStep(
                lambda: self._add_op_combo,
                TeachingTipTailPosition.BOTTOM,
                "处理步骤从这里加",
                "平滑、裁剪、重采样和 FFT 都从这里加入。",
            ),
            OnboardingStep(
                lambda: self._op_list,
                TeachingTipTailPosition.LEFT_BOTTOM,
                "操作链决定顺序",
                "中间列表按顺序执行，右侧预览会跟随当前参数更新。",
            ),
            OnboardingStep(
                lambda: self._save_result_button,
                TeachingTipTailPosition.BOTTOM,
                "确认后再写回",
                "命名结果并选目标列后，再把数据正式写回项目。",
            ),
        ]

    def _extension_panel_splitter(self) -> QSplitter | None:
        return getattr(self, "_page_splitter", None)

    def _extension_panel_visible_sizes(self) -> tuple[int, int]:
        return (
            max(self.width() - self._view_state.extension_panel_width - 24, 640),
            self._view_state.extension_panel_width,
        )

    def _extension_panel_hidden_sizes(self) -> tuple[int, int]:
        return (1, 0)

    def _build_left(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(200)
        panel.setMaximumWidth(300)
        lv = QVBoxLayout(panel)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(6)
        lv.addWidget(make_section_label("当前输入"))
        self._shared_tree_hint = BodyLabel("请通过共享项目树选择处理输入。")
        self._shared_tree_hint.setWordWrap(True)
        self._shared_tree_hint.hide()
        lv.addWidget(self._shared_tree_hint)
        self._src_tree = TreeWidget(self)
        self._src_tree.setHeaderHidden(True)
        self._src_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._src_tree.itemSelectionChanged.connect(self._on_src_selected)
        self._src_tree.hide()
        lv.addWidget(self._src_tree)
        refresh_btn = ToolButton(FIF.SYNC)
        refresh_btn.setToolTip("刷新数据源列表")
        refresh_btn.clicked.connect(self._refresh_tree)
        refresh_btn.hide()
        lv.addWidget(refresh_btn)
        return panel

    def _build_middle(self) -> QWidget:
        panel = CardWidget(self)
        self._tool_panel = panel
        panel.setFixedWidth(WORKBENCH_TOOL_PANEL_WIDTH)
        mv = QVBoxLayout(panel)
        mv.setContentsMargins(14, 14, 14, 14)
        mv.setSpacing(8)

        self._current_input_label = BodyLabel("当前输入: 未选择")
        self._current_input_label.setWordWrap(True)
        self._current_input_label.hide()

        self._input_hint_label = BodyLabel("从共享树双击数据加入“已选择列表”；双/多曲线工具统一使用顶部“选择曲线”。")
        self._input_hint_label.setWordWrap(True)
        self._input_hint_label.hide()

        self._selected_input_state_label = CaptionLabel("当前处理: 未选择", self)
        self._selected_input_state_label.setWordWrap(True)
        self._selected_input_state_label.setStyleSheet(f"color: {secondary_color()};")

        self._selected_input_splitter = QSplitter(Qt.Orientation.Vertical, panel)
        self._selected_input_splitter.setHandleWidth(6)
        self._selected_input_splitter.setChildrenCollapsible(False)
        self._selected_input_splitter.splitterMoved.connect(self._on_selected_input_splitter_moved)
        mv.addWidget(self._selected_input_splitter, 1)

        selected_section = QWidget(self._selected_input_splitter)
        selected_layout = QVBoxLayout(selected_section)
        selected_layout.setContentsMargins(0, 0, 0, 0)
        selected_layout.setSpacing(8)

        selected_layout.addWidget(make_section_label("已选择列表"))
        self._selected_input_list = ListWidget(self)
        self._selected_input_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._selected_input_list.setMinimumHeight(108)
        self._selected_input_list.itemSelectionChanged.connect(self._on_selected_input_list_changed)
        self._selected_input_list.currentItemChanged.connect(lambda _current, _previous: self._on_selected_input_list_changed())
        selected_layout.addWidget(self._selected_input_list, 1)
        selected_layout.addWidget(self._selected_input_state_label)

        selected_row = QHBoxLayout()
        self._btn_clear_inputs = PushButton(FIF.DELETE, "清除", self)
        apply_button_metrics(self._btn_clear_inputs, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        self._btn_clear_inputs.clicked.connect(self._clear_inputs)
        selected_row.addWidget(self._btn_clear_inputs)
        self._btn_remove_selected_inputs = PushButton(FIF.REMOVE, "移除选中", self)
        apply_button_metrics(self._btn_remove_selected_inputs, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        self._btn_remove_selected_inputs.clicked.connect(self._remove_selected_inputs)
        selected_row.addWidget(self._btn_remove_selected_inputs)
        self._btn_selected_up = ToolButton(FIF.UP, self)
        self._btn_selected_up.setToolTip("上移")
        self._btn_selected_up.clicked.connect(self._move_selected_inputs_up)
        self._btn_selected_up.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)
        selected_row.addWidget(self._btn_selected_up)
        self._btn_selected_down = ToolButton(FIF.DOWN, self)
        self._btn_selected_down.setToolTip("下移")
        self._btn_selected_down.clicked.connect(self._move_selected_inputs_down)
        self._btn_selected_down.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)
        selected_row.addWidget(self._btn_selected_down)
        selected_row.addStretch()
        selected_layout.addLayout(selected_row)

        controls_section = QWidget(self._selected_input_splitter)
        controls_layout = QVBoxLayout(controls_section)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)

        controls_layout.addWidget(make_hsep())
        controls_layout.addWidget(make_section_label("操作链"))

        self._pipeline_lines_button = PushButton(FIF.LINK, "选择曲线", self)
        apply_button_metrics(self._pipeline_lines_button, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        self._pipeline_lines_button.clicked.connect(self._choose_pipeline_lines)
        controls_layout.addWidget(self._pipeline_lines_button)

        template_row = QHBoxLayout()
        self._pipeline_combo = ComboBox(self)
        template_row.addWidget(self._pipeline_combo, 1)
        load_tpl_btn = ToolButton(FIF.FOLDER)
        load_tpl_btn.setToolTip("加载模板")
        load_tpl_btn.clicked.connect(self._load_pipeline_from_combo)
        load_tpl_btn.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)
        template_row.addWidget(load_tpl_btn)
        save_as_btn = ToolButton(FIF.ADD)
        save_as_btn.setToolTip("另存为模板")
        save_as_btn.clicked.connect(self._on_save_pipeline_template_as)
        save_as_btn.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)
        template_row.addWidget(save_as_btn)
        overwrite_btn = ToolButton(FIF.SAVE)
        overwrite_btn.setToolTip("覆盖当前模板")
        overwrite_btn.clicked.connect(self._overwrite_current_pipeline)
        overwrite_btn.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)
        template_row.addWidget(overwrite_btn)
        clear_ops_btn = ToolButton(FIF.DELETE)
        clear_ops_btn.setToolTip("清空操作链")
        clear_ops_btn.clicked.connect(self._clear_ops)
        clear_ops_btn.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)
        template_row.addWidget(clear_ops_btn)
        controls_layout.addLayout(template_row)

        self._op_list = ListWidget(self)
        self._op_list.currentRowChanged.connect(self._on_op_selected)
        controls_layout.addWidget(self._op_list, stretch=1)

        btn_row = QHBoxLayout()
        self._add_op_combo = ComboBox(self)
        self._add_op_combo.currentIndexChanged.connect(self._update_add_op_tip)
        btn_row.addWidget(self._add_op_combo, 1)
        add_btn = ToolButton(FIF.ADD)
        add_btn.setToolTip("添加操作")
        add_btn.clicked.connect(self._add_op)
        add_btn.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)
        btn_row.addWidget(add_btn)
        del_btn = ToolButton(FIF.DELETE)
        del_btn.setToolTip("删除选中操作")
        del_btn.clicked.connect(self._remove_op)
        del_btn.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)
        btn_row.addWidget(del_btn)
        up_btn = ToolButton(FIF.UP)
        up_btn.setToolTip("上移")
        up_btn.clicked.connect(self._move_op_up)
        up_btn.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)
        btn_row.addWidget(up_btn)
        dn_btn = ToolButton(FIF.DOWN)
        dn_btn.setToolTip("下移")
        dn_btn.clicked.connect(self._move_op_down)
        dn_btn.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)
        btn_row.addWidget(dn_btn)
        controls_layout.addLayout(btn_row)

        for widget in (self._add_op_combo, add_btn, del_btn, up_btn, dn_btn, load_tpl_btn,
                       save_as_btn, overwrite_btn, clear_ops_btn):
            _install_fluent_tip(widget, widget.toolTip() or self._add_op_combo.toolTip(), ToolTipPosition.BOTTOM)

        for widget in (self._btn_selected_up, self._btn_selected_down):
            _install_fluent_tip(widget, widget.toolTip(), ToolTipPosition.BOTTOM)
        _install_fluent_tip(self._pipeline_lines_button, "为当前 pipeline 的双/多曲线扩展选择输入曲线", ToolTipPosition.BOTTOM)

        controls_layout.addWidget(make_hsep())
        controls_layout.addWidget(make_section_label("操作参数"))
        self._param_stack = QStackedWidget(self)
        controls_layout.addWidget(self._param_stack)
        controls_layout.addStretch()

        export_hint = BodyLabel("导出时会先命名，并选择或新建目标数据文件。", self)
        export_hint.setWordWrap(True)
        export_hint.hide()
        controls_layout.addWidget(export_hint)

        self._save_name_edit = LineEdit(self)
        self._save_name_edit.setPlaceholderText("processed_result")
        self._save_target_combo = ComboBox(self)
        self._save_name_edit.hide()
        self._save_target_combo.hide()

        controls_layout.addWidget(make_hsep())
        export_row = QHBoxLayout()
        self._save_result_button = PrimaryPushButton(FIF.SAVE, "导出数据列")
        self._save_result_button.clicked.connect(self._save_result)
        apply_button_metrics(self._save_result_button, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        export_row.addWidget(self._save_result_button)
        self._save_batch_result_button = PushButton(FIF.SHARE, "批量导出")
        self._save_batch_result_button.clicked.connect(self._save_batch_result)
        apply_button_metrics(self._save_batch_result_button, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        export_row.addWidget(self._save_batch_result_button)
        controls_layout.addLayout(export_row)
        self._selected_input_splitter.setStretchFactor(0, 0)
        self._selected_input_splitter.setStretchFactor(1, 1)
        self._selected_input_splitter.setSizes([400, 600])
        self._refresh_pipeline_templates()
        self._refresh_save_targets()
        return panel

    def _build_right(self) -> QWidget:
        panel = CardWidget(self)
        rv = QVBoxLayout(panel)
        rv.setContentsMargins(14, 14, 14, 14)
        rv.setSpacing(8)
        rv.addWidget(make_section_label("处理预览"))
        if _HAS_MPL:
            self._figure = Figure(figsize=(5, 4))
            self._canvas = FigureCanvas(self._figure)
            self._preview_nav_toolbar = create_navigation_toolbar(
                self._canvas,
                panel,
                sync_callback=self._sync_preview_nav_toggle_states,
            )
            preview_toolbar, preview_buttons = build_preview_toolbar(
                panel,
                button_size=WORKBENCH_BUTTON_HEIGHT,
                reset_callback=self._reset_preview_view,
                zoom_in_callback=lambda: self._zoom_preview_axes(0.8),
                zoom_out_callback=lambda: self._zoom_preview_axes(1.25),
                pan_toggle_callback=self._toggle_preview_pan_mode,
                box_zoom_toggle_callback=self._toggle_preview_box_zoom_mode,
                install_tooltip=lambda widget, text: _install_fluent_tip(widget, text, ToolTipPosition.BOTTOM),
            )
            self._preview_fit_btn = preview_buttons.fit
            self._preview_zoom_in_btn = preview_buttons.zoom_in
            self._preview_zoom_out_btn = preview_buttons.zoom_out
            self._preview_pan_btn = preview_buttons.pan
            self._preview_box_zoom_btn = preview_buttons.box_zoom
            rv.addLayout(preview_toolbar)
            self._canvas.setMinimumHeight(260)
            rv.addWidget(self._canvas, stretch=1)
            self._sync_preview_nav_toggle_states()
        else:
            self._figure = None
            self._canvas = None
            rv.addWidget(BodyLabel("需要 matplotlib"), stretch=1)
        self._stats_label = BodyLabel("（选择数据并配置操作后显示统计）")
        self._stats_label.setWordWrap(True)
        rv.addWidget(self._stats_label)
        return panel

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
        zoom_figure_axes(self._figure, self._canvas, factor, redraw_callback=self._draw_preview)

    def _reset_preview_view(self) -> None:
        self._draw_preview()
        self._sync_preview_nav_toggle_states()

    # ─────────────────────────────────────────────────────────
    # 数据源树
    # ─────────────────────────────────────────────────────────

    def _refresh_tree(self):
        if not hasattr(self, "_src_tree") or self._src_tree is None:
            return
        self._src_tree.clear()
        p = project_manager.current_project
        if p is None:
            return
        img_root = QTreeWidgetItem(["🖼  图像曲线"])
        img_root.setExpanded(True)
        for img in p.images:
            for c in img.curves:
                if c.x_actual:
                    it = QTreeWidgetItem([f"  {img.name} / {c.name}"])
                    it.setData(0, Qt.ItemDataRole.UserRole, ("curve", c.id))
                    img_root.addChild(it)
        self._src_tree.addTopLevelItem(img_root)

        ds_root = QTreeWidgetItem(["📁  数据系列"])
        ds_root.setExpanded(True)
        for data_file in p.data_files:
            for s in data_file.series:
                if s.x:
                    it = QTreeWidgetItem([f"  {data_file.name} / {s.name}"])
                    it.setData(0, Qt.ItemDataRole.UserRole, ("series", s.id))
                    ds_root.addChild(it)
        self._src_tree.addTopLevelItem(ds_root)
        self._refresh_pipeline_templates()

    def _on_src_selected(self):
        items = self._src_tree.selectedItems()
        if not items:
            return
        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        typ, obj_id = data
        p = project_manager.current_project
        if p is None:
            return
        if typ == "curve":
            c = next((c for img in p.images for c in img.curves if c.id == obj_id), None)
            if c:
                self._selected_source_kind = "curve"
                self._selected_source_node_id = obj_id
                self._src_series_batch = [DataSeries(name=c.name, x=list(c.x_actual), y=list(c.y_actual), color=c.color, source="pyline_curve_copy", source_curve_id=c.id)]
                self._src_xs = list(c.x_actual)
                self._src_ys = list(c.y_actual)
                self._selected_src_id = obj_id
                self._current_input_label.setText(f"当前输入: {c.name}")
                self._extension_panel.set_context("数据处理", c.name)
                self._save_name_edit.setText(self._suggest_result_name(c.name))
        elif typ == "series":
            s = p.find_series(obj_id)
            if s:
                self._selected_source_kind = "series"
                self._selected_source_node_id = obj_id
                self._src_series_batch = [s]
                self._src_xs = list(s.x)
                self._src_ys = list(s.y)
                self._selected_src_id = obj_id
                self._current_input_label.setText(f"当前输入: {s.name}")
                self._extension_panel.set_context("数据处理", s.name)
                self._save_name_edit.setText(self._suggest_result_name(s.name))
        self._update_save_action_presentation()
        self._run_pipeline()

    def _resolve_input_payloads(self, kind: str, node_id: str) -> List[Dict[str, Any]]:
        if kind == "data_file":
            container_name = project_manager.format_tree_path_label(node_id, separator="/", omit_root_group=True) or "数据文件"
            payloads = []
            for series in project_manager.get_all_series_from_node(kind, node_id):
                if not series or not series.x:
                    continue
                payloads.append({
                    "kind": "series",
                    "node_id": series.id,
                    "label": f"{container_name}/{series.name}",
                })
            return payloads

        if kind == "image_work":
            container_name = project_manager.format_tree_path_label(node_id, separator="/", omit_root_group=True) or "图像曲线"
            payloads = []
            for series in project_manager.get_all_series_from_node(kind, node_id):
                if not series or not series.x:
                    continue
                item_kind = "curve" if series.source_curve_id else "series"
                item_id = series.source_curve_id or series.id
                payloads.append({
                    "kind": item_kind,
                    "node_id": item_id,
                    "label": f"{container_name}/{series.name}",
                })
            return payloads

        series = project_manager.get_series_from_node(kind, node_id)
        if series is None or not series.x:
            return []
        label = project_manager.format_series_origin_path_label(node_id, separator="/", omit_root_group=True) or series.name
        return [{"kind": kind, "node_id": node_id, "label": label}]

    def _build_series_batch_from_payloads(self, payloads: List[Dict[str, Any]]) -> List[DataSeries]:
        rebuilt: List[DataSeries] = []
        for payload in payloads:
            series = project_manager.get_series_from_node(payload["kind"], payload["node_id"])
            if series is None or not series.x:
                continue
            rebuilt.append(DataSeries(
                name=series.name,
                x=list(series.x),
                y=list(series.y),
                y_err=list(series.y_err) if series.y_err else None,
                x_label=series.x_label,
                y_label=series.y_label,
                color=series.color,
                visible=series.visible,
                source=series.source,
                source_curve_id=series.source_curve_id,
            ))
        return rebuilt

    def _selected_input_node_ids(self) -> List[str]:
        if not hasattr(self, "_selected_input_list"):
            return []
        node_ids: List[str] = []
        for item in self._selected_input_list.selectedItems():
            payload = item.data(Qt.ItemDataRole.UserRole)
            if payload and payload.get("node_id"):
                node_ids.append(str(payload["node_id"]))
        return node_ids

    def _current_selected_input_node_id(self) -> Optional[str]:
        if not hasattr(self, "_selected_input_list"):
            return None
        item = self._selected_input_list.currentItem()
        if item is None:
            return None
        payload = item.data(Qt.ItemDataRole.UserRole)
        if not payload:
            return None
        node_id = payload.get("node_id")
        return str(node_id) if node_id else None

    def _active_input_payloads(self, *, prefer_current: bool = False) -> List[Dict[str, Any]]:
        selected_ids = set(self._selected_input_node_ids())
        if selected_ids:
            active_payloads = [payload for payload in self._selected_inputs if payload["node_id"] in selected_ids]
        else:
            active_payloads = list(self._selected_inputs)
        if not prefer_current:
            return active_payloads
        current_node_id = self._current_selected_input_node_id()
        if not current_node_id:
            return active_payloads
        current_payload = next((payload for payload in active_payloads if payload["node_id"] == current_node_id), None)
        if current_payload is None:
            return active_payloads
        return [current_payload] + [payload for payload in active_payloads if payload["node_id"] != current_node_id]

    def _refresh_input_dependent_param_widgets(self) -> None:
        for widget in self._param_widgets:
            refresh = getattr(widget, "refresh_input_choices", None)
            if callable(refresh):
                refresh()

    def _current_pipeline_definition(self):
        return build_pipeline_extension_definition(self._ops)

    def _pipeline_selected_labels(self) -> List[str]:
        label_map = {payload["node_id"]: payload["label"] for payload in self._selected_inputs}
        return [label_map[node_id] for node_id in self._pipeline_selected_node_ids if node_id in label_map]

    def _pipeline_lines_list(self) -> List[int]:
        index_map = {payload["node_id"]: index + 1 for index, payload in enumerate(self._selected_inputs)}
        return [index_map[node_id] for node_id in self._pipeline_selected_node_ids if node_id in index_map]

    def _sync_pipeline_lines_state(self) -> None:
        self._pipeline_selected_node_ids = [
            node_id for node_id in self._pipeline_selected_node_ids
            if any(payload["node_id"] == node_id for payload in self._selected_inputs)
        ]
        definition = self._current_pipeline_definition()
        lower, upper = definition.lines_number
        requires_multiline_selection = upper == -1 or upper > 1
        self._pipeline_lines_button.setEnabled(requires_multiline_selection and bool(self._selected_inputs))
        if not requires_multiline_selection:
            self._pipeline_lines_button.setToolTip("当前操作链按已选择列表中的当前选中项运行")
            return
        labels = self._pipeline_selected_labels()
        if labels:
            preview = "；".join(labels[:3]) + (" …" if len(labels) > 3 else "")
            self._pipeline_lines_button.setToolTip(f"当前已选曲线: {preview}")
            return
        if not self._selected_inputs:
            self._pipeline_lines_button.setToolTip("当前没有可选曲线")
            return
        range_text = f"{lower} 条以上" if upper == -1 else (f"{lower}-{upper} 条" if lower != upper else f"{lower} 条")
        self._pipeline_lines_button.setToolTip(f"当前操作链需要选择 {range_text} 曲线")

    def _choose_pipeline_lines(self) -> None:
        definition = self._current_pipeline_definition()
        lower, upper = definition.lines_number
        if upper != -1 and upper <= 1:
            return
        labels = [payload.get("label", "未命名曲线") for payload in self._selected_inputs]
        if not labels:
            return
        from ui.widgets.extension_options_form import _LineSelectionDialog

        selected = self._pipeline_lines_list()
        chosen, accepted = _LineSelectionDialog.get_indices(
            self,
            "选择曲线",
            labels,
            selected_indices=selected,
            lines_number=definition.lines_number,
            selected_label="已选中",
            available_label="候选区",
        )
        if not accepted:
            return
        self._pipeline_selected_node_ids = [
            self._selected_inputs[index - 1]["node_id"]
            for index in chosen
            if 1 <= index <= len(self._selected_inputs)
        ]
        self._sync_pipeline_lines_state()
        self._run_pipeline()

    def _refresh_param_stack_height(self) -> None:
        current_widget = self._param_stack.currentWidget() if hasattr(self, "_param_stack") else None
        if current_widget is None:
            self._param_stack.setMinimumHeight(0)
            self._param_stack.setMaximumHeight(0)
            self._param_stack.updateGeometry()
            return
        target_height = max(0, current_widget.sizeHint().height())
        max_height = current_widget.maximumHeight()
        if max_height <= 0 or max_height >= 16777215:
            max_height = target_height
        self._param_stack.setMinimumHeight(min(target_height, max_height))
        self._param_stack.setMaximumHeight(max_height)
        self._param_stack.updateGeometry()

    def _rebuild_source_series_batch(self) -> None:
        active_payloads = self._preview_input_payloads()
        rebuilt = self._build_series_batch_from_payloads(active_payloads)
        self._src_series_batch = rebuilt
        preview = rebuilt[0] if rebuilt else None
        self._src_xs = list(preview.x) if preview is not None else []
        self._src_ys = list(preview.y) if preview is not None else []

    def _pairing_preview_payloads(self) -> List[Dict[str, Any]]:
        if not self._selected_inputs:
            return []
        for op in self._ops:
            op_type = str(op.get("type", "") or "")
            params = self._normalized_operation_params(op_type, op.get("params", {}) or {})
            if not self._is_pairing_operation(op_type, params):
                continue
            indices = normalize_extension_lines_list(params.get("lines_list")) if "lines_list" in params else []
            payloads: List[Dict[str, Any]] = []
            for index in indices:
                try:
                    offset = int(index) - 1
                except Exception:
                    continue
                if 0 <= offset < len(self._selected_inputs):
                    payloads.append(self._selected_inputs[offset])
            return payloads or list(self._selected_inputs)
        return []

    def _preview_input_payloads(self) -> List[Dict[str, Any]]:
        pairing_payloads = self._pairing_preview_payloads()
        if pairing_payloads:
            return pairing_payloads
        return self._active_input_payloads(prefer_current=True)

    def _normalized_operation_params(self, op_type: str, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        normalized = dict(params or {})
        if op_type == "resample" and "target_line" not in normalized and "target_index" in normalized:
            normalized["target_line"] = normalized.pop("target_index")
        explicit_lines = self._pipeline_lines_list() or (
            normalize_extension_lines_list(normalized.get("lines_list")) if "lines_list" in normalized else []
        )
        if op_type == "pairwise_compute" and not explicit_lines:
            indices: List[int] = []
            for key in ("primary_index", "secondary_index"):
                try:
                    value = int(normalized.get(key))
                except Exception:
                    continue
                if value >= 1:
                    indices.append(value)
            if indices:
                normalized["lines_list"] = indices
        elif explicit_lines:
            normalized["lines_list"] = explicit_lines
        return normalized

    def _update_selected_input_state_label(self) -> None:
        active_payloads = self._active_input_payloads()
        if not self._selected_inputs:
            self._selected_input_state_label.setText("当前处理: 未选择")
            return
        if not active_payloads:
            self._selected_input_state_label.setText("当前处理: 全部已选择项")
            return
        labels = [payload["label"] for payload in active_payloads]
        self._selected_input_state_label.setText("当前处理: " + "；".join(labels[:3]) + (" …" if len(labels) > 3 else ""))

    def _sync_selected_input_state(self) -> None:
        self._rebuild_source_series_batch()
        self._update_selected_input_state_label()
        self._sync_pipeline_lines_state()
        if not self._selected_inputs:
            self._selected_src_id = None
            self._selected_source_kind = None
            self._selected_source_node_id = None
            self._current_input_label.setText("当前输入: 未选择")
            self._extension_panel.set_context("数据处理", "未选择输入")
            self._refresh_save_targets()
            self._update_save_action_presentation()
            self._refresh_input_dependent_param_widgets()
            return

        primary = self._selected_inputs[0]
        active_count = len(self._active_input_payloads())
        total_count = len(self._selected_inputs)
        self._selected_src_id = primary["node_id"]
        self._selected_source_kind = primary["kind"]
        self._selected_source_node_id = primary["node_id"]
        if total_count == 1:
            self._current_input_label.setText(f"当前输入: {primary['label']}")
            self._extension_panel.set_context("数据处理", primary["label"])
        else:
            self._current_input_label.setText(f"当前输入: {primary['label']}（已选择 {total_count} 条，当前处理 {active_count or total_count} 条）")
            self._extension_panel.set_context("数据处理", f"{primary['label']} 等 {total_count} 条输入")
        self._refresh_save_targets()
        self._update_save_action_presentation()
        self._refresh_input_dependent_param_widgets()

    def _rebuild_selected_input_list(self, selected_ids: Optional[set[str]] = None, current_node_id: Optional[str] = None) -> None:
        if selected_ids is None:
            selected_ids = set(self._selected_input_node_ids())
        if current_node_id is None:
            current_node_id = self._current_selected_input_node_id()
        self._selected_input_list.blockSignals(True)
        self._selected_input_list.clear()
        current_item: Optional[QListWidgetItem] = None
        for payload in self._selected_inputs:
            item = QListWidgetItem(payload["label"])
            item.setData(Qt.ItemDataRole.UserRole, {"node_id": payload["node_id"], "kind": payload["kind"]})
            item.setToolTip(payload["label"])
            self._selected_input_list.addItem(item)
            if payload["node_id"] in selected_ids:
                item.setSelected(True)
            if payload["node_id"] == current_node_id:
                current_item = item
        if current_item is not None:
            self._selected_input_list.setCurrentItem(current_item, QItemSelectionModel.SelectionFlag.NoUpdate)
        self._selected_input_list.blockSignals(False)
        self._sync_selected_input_state()

    def _append_inputs_from_tree_node(self, kind: str, node_id: str) -> bool:
        payloads = self._resolve_input_payloads(kind, node_id)
        if not payloads:
            return False

        selected_ids = set(self._selected_input_node_ids())
        added = False
        for payload in payloads:
            if any(item["node_id"] == payload["node_id"] for item in self._selected_inputs):
                selected_ids.add(payload["node_id"])
                continue
            self._selected_inputs.append(payload)
            selected_ids.add(payload["node_id"])
            added = True

        self._rebuild_selected_input_list(selected_ids)
        if added:
            self._save_name_edit.setText(self._suggest_result_name())
            self._run_pipeline()
        return True

    def _clear_inputs(self) -> None:
        self._selected_inputs.clear()
        self._rebuild_selected_input_list(set())
        self._pipeline_warnings = []
        self._out_series_batch = []
        self._out_xs = []
        self._out_ys = []
        self._save_name_edit.clear()
        self._draw_preview()
        self._stats_label.setText("（选择数据并配置操作后显示统计）")

    def _remove_selected_inputs(self) -> None:
        to_remove = set(self._selected_input_node_ids())
        if not to_remove:
            return
        self._selected_inputs = [item for item in self._selected_inputs if item["node_id"] not in to_remove]
        self._rebuild_selected_input_list(set())
        self._save_name_edit.setText(self._suggest_result_name())
        self._run_pipeline()

    def _move_selected_inputs_to_top(self) -> None:
        self._move_selected_inputs("top")

    def _move_selected_inputs_up(self) -> None:
        self._move_selected_inputs("up")

    def _move_selected_inputs_down(self) -> None:
        self._move_selected_inputs("down")

    def _move_selected_inputs_to_bottom(self) -> None:
        self._move_selected_inputs("bottom")

    def _move_selected_inputs(self, mode: str) -> None:
        selected_ids = self._selected_input_node_ids()
        if not selected_ids:
            return
        selected_set = set(selected_ids)
        items = list(self._selected_inputs)
        if mode == "top":
            items = [item for item in items if item["node_id"] in selected_set] + [item for item in items if item["node_id"] not in selected_set]
        elif mode == "bottom":
            items = [item for item in items if item["node_id"] not in selected_set] + [item for item in items if item["node_id"] in selected_set]
        elif mode == "up":
            for index in range(1, len(items)):
                if items[index]["node_id"] in selected_set and items[index - 1]["node_id"] not in selected_set:
                    items[index - 1], items[index] = items[index], items[index - 1]
        elif mode == "down":
            for index in range(len(items) - 2, -1, -1):
                if items[index]["node_id"] in selected_set and items[index + 1]["node_id"] not in selected_set:
                    items[index], items[index + 1] = items[index + 1], items[index]
        else:
            return
        self._selected_inputs = items
        self._rebuild_selected_input_list(selected_set)
        self._run_pipeline()

    def _on_selected_input_list_changed(self) -> None:
        self._sync_selected_input_state()
        self._save_name_edit.setText(self._suggest_result_name())
        self._run_pipeline()

    def _supports_batch_export(self) -> bool:
        if len(self._selected_inputs) <= 1:
            return False
        return not any(self._is_pairing_operation(op.get("type", ""), op.get("params", {})) for op in self._ops)

    def _update_save_action_presentation(self) -> None:
        self._save_result_button.setText("导出数据列")
        if hasattr(self, "_save_batch_result_button"):
            batch_supported = self._supports_batch_export()
            self._save_batch_result_button.setEnabled(batch_supported)
            self._save_batch_result_button.setToolTip("" if batch_supported else "当前操作链不支持批量导出")

    # ─────────────────────────────────────────────────────────
    # 操作链管理
    # ─────────────────────────────────────────────────────────

    def _clear_ops(self):
        """清空当前操作链。"""
        for widget in self._param_widgets:
            self._param_stack.removeWidget(widget)
            widget.deleteLater()
        self._param_widgets.clear()
        self._ops.clear()
        self._op_list.clear()
        self._pipeline_selected_node_ids.clear()
        self._sync_pipeline_lines_state()
        self._refresh_param_stack_height()
        self._save_name_edit.setText(self._suggest_result_name())
        self._run_pipeline()

    def _add_op(self):
        idx = self._add_op_combo.currentIndex()
        if not (0 <= idx < len(self._processing_op_types)):
            return
        op_type = self._processing_op_types[idx]
        self._add_operation_to_chain(op_type, self._default_params_for_processing_type(op_type))

    def _is_pairing_operation(self, op_type: str, params: Optional[Dict[str, Any]] = None) -> bool:
        del params
        extension = extension_registry.get_processing(op_type)
        if extension is None:
            return False
        lines_number = extension_lines_number(extension)
        if lines_number is None:
            return False
        _lower, upper = lines_number
        return upper == -1 or upper > 1

    def _can_add_operation(self, op_type: str, params: Optional[Dict[str, Any]] = None) -> bool:
        if not self._is_pairing_operation(op_type, params):
            return True
        if any(self._is_pairing_operation(op.get("type", ""), op.get("params", {})) for op in self._ops):
            InfoBar.warning(
                "添加失败",
                "pipeline 中不应有超过一个双曲线处理工具或多曲线处理扩展",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return False
        return True

    def _add_operation_to_chain(self, op_type: str, params: Optional[Dict[str, Any]] = None) -> None:
        if not self._can_add_operation(op_type, params):
            return
        op_label = self._op_label_for_type(op_type)
        pw = _make_param_widget(op_type, self, self._run_pipeline)
        if params and hasattr(pw, "set_params"):
            pw.set_params(dict(params))
        self._param_widgets.append(pw)
        self._param_stack.addWidget(pw)
        self._ops.append({
            "type": op_type,
            "params": pw.get_params(),
            "config_id": getattr(pw, "current_settings_config_id", lambda: None)(),
        })
        self._op_list.addItem(op_label)
        self._op_list.setCurrentRow(len(self._ops) - 1)
        self._sync_pipeline_lines_state()
        self._refresh_param_stack_height()
        self._save_name_edit.setText(self._suggest_result_name())
        self._run_pipeline()

    def _remove_op(self):
        row = self._op_list.currentRow()
        if row < 0 or row >= len(self._ops):
            return
        self._ops.pop(row)
        pw = self._param_widgets.pop(row)
        self._param_stack.removeWidget(pw)
        pw.deleteLater()
        self._op_list.takeItem(row)
        self._sync_pipeline_lines_state()
        self._refresh_param_stack_height()
        self._save_name_edit.setText(self._suggest_result_name())
        self._run_pipeline()

    def _move_op_up(self):
        row = self._op_list.currentRow()
        if row <= 0:
            return
        self._ops[row], self._ops[row - 1] = self._ops[row - 1], self._ops[row]
        self._param_widgets[row], self._param_widgets[row - 1] = (
            self._param_widgets[row - 1], self._param_widgets[row])
        la, lb = self._op_list.item(row).text(), self._op_list.item(row - 1).text()
        self._op_list.item(row).setText(lb)
        self._op_list.item(row - 1).setText(la)
        self._op_list.setCurrentRow(row - 1)
        self._save_name_edit.setText(self._suggest_result_name())
        self._run_pipeline()

    def _move_op_down(self):
        row = self._op_list.currentRow()
        if row < 0 or row >= len(self._ops) - 1:
            return
        self._ops[row], self._ops[row + 1] = self._ops[row + 1], self._ops[row]
        self._param_widgets[row], self._param_widgets[row + 1] = (
            self._param_widgets[row + 1], self._param_widgets[row])
        la, lb = self._op_list.item(row).text(), self._op_list.item(row + 1).text()
        self._op_list.item(row).setText(lb)
        self._op_list.item(row + 1).setText(la)
        self._op_list.setCurrentRow(row + 1)
        self._save_name_edit.setText(self._suggest_result_name())
        self._run_pipeline()

    def _on_op_selected(self, row: int):
        if 0 <= row < len(self._param_widgets):
            self._param_stack.setCurrentWidget(self._param_widgets[row])
        self._refresh_param_stack_height()

    # ─────────────────────────────────────────────────────────
    # 管道执行 + 预览
    # ─────────────────────────────────────────────────────────

    def _run_pipeline(self):
        """防抖入口：重置 300ms 计时器，停止高频连续触发。"""
        self._run_timer.start()

    def _run_pipeline_now(self):
        if not self._src_series_batch:
            self._pipeline_warnings = []
            self._out_series_batch = []
            self._out_xs = []
            self._out_ys = []
            self._draw_preview()
            self._set_stats_message("（选择数据并配置操作后显示统计）")
            self._update_save_action_presentation()
            return
        for op, pw in zip(self._ops, self._param_widgets):
            merged_params = dict(op.get("params", {}) or {})
            merged_params.update(pw.get_params())
            op["params"] = self._normalized_operation_params(str(op.get("type", "") or ""), merged_params)
            op["config_id"] = getattr(pw, "current_settings_config_id", lambda: None)()
        try:
            preview_payloads = self._preview_input_payloads()
            self._out_series_batch, self._pipeline_warnings = self._build_output_series_batch(
                preview_payloads,
                self._selected_inputs,
            )
            preview_series = self._out_series_batch[0] if self._out_series_batch else None
            self._out_xs = list(preview_series.x) if preview_series is not None else []
            self._out_ys = list(preview_series.y) if preview_series is not None else []
        except Exception as e:
            self._pipeline_warnings = []
            self._out_series_batch = []
            self._out_xs = []
            self._out_ys = []
            self._set_stats_message(f"处理错误: {e}", is_error=True)
            self._update_save_action_presentation()
            return
        self._draw_preview()
        self._update_stats()
        self._update_save_action_presentation()

    def _series_to_line_payload(self, source_series: DataSeries) -> Dict[str, Any]:
        return {
            "name": source_series.name,
            "x": list(source_series.x),
            "y": list(source_series.y),
            "x_label": source_series.x_label,
            "y_label": source_series.y_label,
            "color": source_series.color,
            "visible": source_series.visible,
            "source_curve_id": source_series.source_curve_id,
        }

    def _build_output_series_batch(
        self,
        active_payloads: List[Dict[str, Any]],
        selected_payloads: Optional[List[Dict[str, Any]]] = None,
    ) -> tuple[List[DataSeries], List[str]]:
        source_templates = self._build_series_batch_from_payloads(active_payloads)
        if not source_templates:
            return [], []
        all_series = self._build_series_batch_from_payloads(selected_payloads or active_payloads)
        output_lines, warnings = apply_pipeline_to_lines(
            [self._series_to_line_payload(series) for series in source_templates],
            self._ops,
            selected_lines=[self._series_to_line_payload(series) for series in all_series],
        )
        template_series = source_templates or all_series
        rebuilt = [
            DataSeries(
                name=str(line.get("name", source_series.name) or source_series.name),
                x=list(line.get("x", []) or []),
                y=list(line.get("y", []) or []),
                x_label=str(line.get("x_label", source_series.x_label) or source_series.x_label),
                y_label=str(line.get("y_label", source_series.y_label) or source_series.y_label),
                color=str(line.get("color", source_series.color) or source_series.color),
                visible=bool(line.get("visible", source_series.visible)),
                source="computed",
                source_curve_id=line.get("source_curve_id", source_series.source_curve_id),
            )
            for line, source_series in zip(
                output_lines,
                template_series + [template_series[0]] * max(0, len(output_lines) - len(template_series)),
            )
        ]
        return rebuilt, warnings

    def _draw_preview(self):
        if not _HAS_MPL or self._figure is None:
            return
        self._figure.clear()
        ax = self._figure.add_subplot(111)
        dark = isDarkTheme()
        bg = preview_canvas_background_color(dark)
        fg = preview_canvas_foreground_color(dark)
        gc = preview_canvas_grid_color(dark)
        self._apply_preview_host_background()
        self._figure.patch.set_facecolor(bg)
        ax.set_facecolor(bg)
        ax.tick_params(colors=fg, labelcolor=fg)
        for sp in ax.spines.values():
            sp.set_edgecolor(fg)
        ax.grid(True, color=gc, linestyle="--", linewidth=0.5, alpha=0.6)
        _MAX_PTS = 2000
        src_label = "原始（预览当前首条）" if len(self._src_series_batch) > 1 else "原始"
        out_label = "处理后（预览当前首条）" if len(self._out_series_batch) > 1 else "处理后"
        if self._src_xs:
            sx, sy = _downsample(self._src_xs, self._src_ys, _MAX_PTS)
            ax.plot(sx, sy, color="#888888",
                    linestyle="--", linewidth=1.0, alpha=0.6, label=src_label)
        if self._out_xs:
            ox, oy = _downsample(self._out_xs, self._out_ys, _MAX_PTS)
            ax.plot(ox, oy, color="#0078D4",
                    linewidth=1.5, label=out_label)
        if self._src_xs or self._out_xs:
            ax.legend(facecolor=bg, edgecolor=fg, labelcolor=fg, fontsize=8)
        self._canvas.draw()

    def _apply_preview_host_background(self) -> None:
        if getattr(self, "_canvas", None) is None:
            return
        background = preview_canvas_background_color(isDarkTheme())
        self._canvas.setStyleSheet(f"background: {background};")

    def _update_stats(self):
        n = len(self._out_ys)
        if n == 0:
            self._set_stats_message("输出为空")
            return
        try:
            import numpy as np
            a = np.asarray(self._out_ys, dtype=float)
            y_min, y_max, mean, std = float(a.min()), float(a.max()), float(a.mean()), float(a.std())
        except ImportError:
            y_min, y_max = min(self._out_ys), max(self._out_ys)
            mean = sum(self._out_ys) / n
            std = math.sqrt(sum((v - mean) ** 2 for v in self._out_ys) / n)
        prefix = f"共处理 {len(self._out_series_batch)} 条数据系列；预览 " if len(self._out_series_batch) > 1 else ""
        stats_text = f"{prefix}输出 N={n}  Y: [{y_min:.4g}, {y_max:.4g}]  均值={mean:.4g}  σ={std:.4g}"
        if self._pipeline_warnings:
            stats_text += "\n提示: " + "；".join(self._pipeline_warnings)
        self._set_stats_message(stats_text)

    def _set_stats_message(self, text: str, *, is_error: bool = False) -> None:
        self._stats_label.setStyleSheet("color: #d13438;" if is_error else "")
        self._stats_label.setText(text)

    # ─────────────────────────────────────────────────────────
    # 保存结果
    # ─────────────────────────────────────────────────────────

    def _save_result(self):
        if not self._out_series_batch:
            InfoBar.warning("提示", "没有可保存的结果", parent=self, position=InfoBarPosition.TOP)
            return
        p = project_manager.current_project
        if p is None:
            InfoBar.warning("提示", "请先打开项目", parent=self, position=InfoBarPosition.TOP)
            return

        default_name = self._default_single_export_name()
        series = self._build_preview_output_series(default_name)
        if series is None:
            InfoBar.warning("提示", "当前没有可导出的预览数据列", parent=self, position=InfoBarPosition.TOP)
            return
        export_plan = choose_data_export_plan(
            self,
            title="导出数据列",
            default_export_name=default_name,
            default_file_name=f"{default_name}.process",
            file_suffix=".process",
            allow_append_to_existing=True,
            show_export_name=True,
        )
        if export_plan is None:
            return
        result_name = export_plan.export_name.strip() or default_name
        self._save_name_edit.setText(result_name)
        series.name = result_name
        if export_plan.target_data_file_id:
            target_file = p.find_data_file(export_plan.target_data_file_id)
            if target_file is None or not project_manager.add_series_to_data_file(export_plan.target_data_file_id, series):
                message = project_manager.get_last_error_message() or "未能追加到目标数据文件"
                InfoBar.error("保存失败", message, parent=self, position=InfoBarPosition.TOP)
                return
            message = f"{series.name} -> {target_file.name}"
        else:
            data_file = DataFile(name=export_plan.new_data_file_name or f"{result_name}.process", series=[series])
            node = project_manager.add_data_file(data_file, parent_id=export_plan.new_parent_id)
            if node is None:
                message = project_manager.get_last_error_message() or "未能创建处理结果数据文件"
                InfoBar.error("保存失败", message, parent=self, position=InfoBarPosition.TOP)
                return
            message = f"{series.name} -> {data_file.name}"

        self._refresh_save_targets()
        self.project_modified.emit()
        InfoBar.success("已保存", message, parent=self, position=InfoBarPosition.TOP)

    def _suggest_result_name(self, source_name: Optional[str] = None) -> str:
        base_name = source_name
        if not base_name:
            active_payloads = self._active_input_payloads(prefer_current=True)
            if active_payloads:
                base_name = active_payloads[0]["label"]
        if not base_name and self._selected_src_id:
            series = project_manager.get_series_from_node("series", self._selected_src_id)
            base_name = series.name if series is not None else None
        if not base_name:
            base_name = "processed"
        op_suffix = "_".join(op["type"] for op in self._ops[:3])
        return f"{base_name}_{op_suffix}" if op_suffix else base_name

    def _default_single_export_name(self) -> str:
        preview_series = self._out_series_batch[0] if self._out_series_batch else None
        preview_name = str(getattr(preview_series, "name", "") or "").strip()
        if preview_name:
            return preview_name
        return self._save_name_edit.text().strip() or self._suggest_result_name()

    def _refresh_save_targets(self) -> None:
        if not hasattr(self, "_save_target_combo"):
            return
        current_id = self._selected_save_target_id()
        self._save_target_combo.clear()
        self._save_target_ids = [None]
        self._save_target_combo.addItem("新建数据文件")
        p = project_manager.current_project
        if p is None:
            return
        selected_index = 0
        for index, data_file in enumerate(p.data_files, start=1):
            self._save_target_combo.addItem(f"追加到: {data_file.name}")
            self._save_target_ids.append(data_file.id)
            if data_file.id == current_id:
                selected_index = index
        self._save_target_combo.setCurrentIndex(selected_index)

    def _selected_save_target_id(self) -> Optional[str]:
        if not hasattr(self, "_save_target_combo"):
            return None
        idx = self._save_target_combo.currentIndex()
        if idx < 0 or idx >= len(self._save_target_ids):
            return None
        return self._save_target_ids[idx]

    def _update_add_op_tip(self, idx: int) -> None:
        if not (0 <= idx < len(self._processing_op_types)):
            return
        op_type = self._processing_op_types[idx]
        self._add_op_combo.setToolTip(self._processing_op_hints.get(op_type, ""))
        if hasattr(self, "_extension_panel"):
            self._extension_panel.set_entries(
                self._processing_extension_entries(),
                saved_options=self._processing_extension_options,
                current_type=op_type if extension_registry.get_processing(op_type) else None,
            )

    def _build_preview_output_series(self, name: str) -> Optional[DataSeries]:
        preview_series = self._out_series_batch[0] if self._out_series_batch else None
        if preview_series is None and not self._out_xs:
            return None
        return DataSeries(
            name=name,
            x=list(preview_series.x) if preview_series is not None else list(self._out_xs),
            y=list(preview_series.y) if preview_series is not None else list(self._out_ys),
            x_label=preview_series.x_label if preview_series is not None else "X",
            y_label=preview_series.y_label if preview_series is not None else "Y",
            color=preview_series.color if preview_series is not None else "#0078D4",
            visible=preview_series.visible if preview_series is not None else True,
            source="computed",
            source_curve_id=preview_series.source_curve_id if preview_series is not None else None,
        )

    def _save_batch_result(self) -> None:
        if not self._supports_batch_export():
            InfoBar.warning("提示", "当前操作链不支持批量导出", parent=self, position=InfoBarPosition.TOP)
            return
        p = project_manager.current_project
        if p is None:
            InfoBar.warning("提示", "请先打开项目", parent=self, position=InfoBarPosition.TOP)
            return
        try:
            output_series_batch, _warnings = self._build_output_series_batch(self._selected_inputs, self._selected_inputs)
        except Exception as e:
            InfoBar.error("批量导出失败", str(e), parent=self, position=InfoBarPosition.TOP)
            return
        if not output_series_batch:
            InfoBar.warning("提示", "没有可批量导出的结果", parent=self, position=InfoBarPosition.TOP)
            return
        default_name = self._save_name_edit.text().strip() or self._suggest_result_name()
        export_plan = choose_data_export_batch_plan(
            self,
            title="批量导出数据列",
            source_labels=[payload["label"] for payload in self._selected_inputs[: len(output_series_batch)]],
            default_export_names=[series.name for series in output_series_batch],
            default_file_name=f"{default_name}.process",
            file_suffix=".process",
            allow_append_to_existing=True,
        )
        if export_plan is None:
            return
        normalized_names = [project_manager._normalize_name_key(name) for name in export_plan.export_names]
        if any(not name for name in normalized_names) or len(set(normalized_names)) != len(normalized_names):
            InfoBar.error("批量导出失败", "批量导出名称不能为空且不能重复", parent=self, position=InfoBarPosition.TOP)
            return
        named_series = [
            DataSeries(
                name=export_name,
                x=list(series.x),
                y=list(series.y),
                x_label=series.x_label,
                y_label=series.y_label,
                color=series.color,
                visible=series.visible,
                source="computed",
                source_curve_id=series.source_curve_id,
            )
            for series, export_name in zip(output_series_batch, export_plan.export_names)
        ]
        if export_plan.target_data_file_id:
            target_file = p.find_data_file(export_plan.target_data_file_id)
            if target_file is None:
                InfoBar.error("批量导出失败", "未找到目标数据文件", parent=self, position=InfoBarPosition.TOP)
                return
            existing_names = {project_manager._normalize_name_key(series.name) for series in target_file.series}
            conflict_names = [series.name for series in named_series if project_manager._normalize_name_key(series.name) in existing_names]
            if conflict_names:
                InfoBar.error(
                    "批量导出失败",
                    "目标数据文件中已存在同名数据列: " + "、".join(conflict_names),
                    parent=self,
                    position=InfoBarPosition.TOP,
                )
                return
            for series in named_series:
                if not project_manager.add_series_to_data_file(export_plan.target_data_file_id, series):
                    message = project_manager.get_last_error_message() or "未能追加到目标数据文件"
                    InfoBar.error("批量导出失败", message, parent=self, position=InfoBarPosition.TOP)
                    return
            message = f"{len(named_series)} 条数据系列 -> {target_file.name}"
        else:
            data_file = DataFile(
                name=export_plan.new_data_file_name or f"{default_name}.process",
                series=named_series,
            )
            node = project_manager.add_data_file(data_file, parent_id=export_plan.new_parent_id)
            if node is None:
                message = project_manager.get_last_error_message() or "未能创建处理结果数据文件"
                InfoBar.error("批量导出失败", message, parent=self, position=InfoBarPosition.TOP)
                return
            message = f"{len(named_series)} 条数据系列 -> {data_file.name}"

        self._refresh_save_targets()
        self.project_modified.emit()
        InfoBar.success("已保存", message, parent=self, position=InfoBarPosition.TOP)

    def _processing_extension_entries(self) -> List[dict]:
        entries: List[dict] = []
        for extension in extension_registry.list_processing():
            entry = build_extension_entry(extension)
            if not entry.get("listed", True):
                continue
            entries.append(entry)
        return sorted(entries, key=self._processing_entry_sort_key)

    @staticmethod
    def _processing_entry_sort_key(entry: dict) -> tuple[int, int, str, str]:
        type_id = str(entry.get("type") or "")
        if type_id in _PREFERRED_PROCESSING_ORDER:
            return (0, _PREFERRED_PROCESSING_ORDER.index(type_id), "", type_id)
        return (1, len(_PREFERRED_PROCESSING_ORDER), str(entry.get("name") or type_id).casefold(), type_id)

    def _refresh_processing_extensions(self) -> None:
        current_type = None
        if hasattr(self, "_add_op_combo") and 0 <= self._add_op_combo.currentIndex() < len(self._processing_op_types):
            current_type = self._processing_op_types[self._add_op_combo.currentIndex()]
        entries = self._processing_extension_entries()
        self._processing_op_labels = [str(entry.get("name") or entry.get("type") or "处理") for entry in entries]
        self._processing_op_types = [str(entry.get("type") or "") for entry in entries]
        self._processing_label_map = {
            str(entry.get("type") or ""): str(entry.get("name") or entry.get("type") or "处理")
            for entry in entries
            if str(entry.get("type") or "")
        }
        self._processing_op_hints = {
            str(entry.get("type") or ""): str(entry.get("description") or self._processing_label_map.get(str(entry.get("type") or ""), "处理扩展"))
            for entry in entries
            if str(entry.get("type") or "")
        }
        self._add_op_combo.blockSignals(True)
        self._add_op_combo.clear()
        self._add_op_combo.addItems(self._processing_op_labels)
        if current_type in self._processing_op_types:
            self._add_op_combo.setCurrentIndex(self._processing_op_types.index(current_type))
        elif self._processing_op_types:
            self._add_op_combo.setCurrentIndex(0)
        self._add_op_combo.blockSignals(False)
        self._update_add_op_tip(self._add_op_combo.currentIndex())
        self._extension_panel.set_entries(
            self._processing_extension_entries(),
            saved_options=self._processing_extension_options,
            current_type=current_type if extension_registry.get_processing(current_type or "") else None,
        )

    def refresh_processing_extensions(self) -> None:
        self._refresh_processing_extensions()

    def _reload_processing_extensions(self) -> None:
        report = reload_configured_extensions()
        self._refresh_processing_extensions()
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

    def _op_label_for_type(self, op_type: str) -> str:
        if op_type in self._processing_label_map:
            return self._processing_label_map[op_type]
        extension = extension_registry.get_processing(op_type)
        if extension is not None:
            return extension.name
        return op_type or "?"

    def _default_params_for_processing_type(self, op_type: str) -> Dict[str, Any]:
        extension = extension_registry.get_processing(op_type)
        if extension is None:
            return {}
        entry = build_extension_entry(extension)
        return dict(self._processing_extension_options.get(op_type, entry.get("resolved_options") or {}))

    def _set_add_op_combo_type(self, op_type: str) -> None:
        if op_type not in self._processing_op_types:
            return
        self._add_op_combo.setCurrentIndex(self._processing_op_types.index(op_type))

    def _on_processing_extension_apply(self, type_id: str, options: Dict[str, Any]) -> None:
        self._processing_extension_options[type_id] = dict(options)
        self._set_add_op_combo_type(type_id)
        self._add_operation_to_chain(type_id, options)
        InfoBar.success("已添加", f"{self._op_label_for_type(type_id)} 已加入操作链", parent=self, position=InfoBarPosition.TOP)

    def _refresh_pipeline_templates(self) -> None:
        current_id = self._current_pipeline_id
        self._pipeline_combo.clear()
        self._pipeline_template_ids.clear()
        selected_index = -1
        for index, pipeline in enumerate(global_assets.list_saved_pipelines()):
            self._pipeline_combo.addItem(pipeline.name)
            self._pipeline_template_ids.append(pipeline.id)
            if pipeline.id == current_id:
                selected_index = index
        if selected_index >= 0:
            self._pipeline_combo.setCurrentIndex(selected_index)

    def _selected_pipeline_id(self) -> Optional[str]:
        idx = self._pipeline_combo.currentIndex()
        if idx < 0 or idx >= len(self._pipeline_template_ids):
            return None
        return self._pipeline_template_ids[idx]

    def _load_pipeline_from_combo(self) -> None:
        pipeline_id = self._selected_pipeline_id()
        if not pipeline_id:
            return
        self.load_pipeline(pipeline_id)

    def _save_pipeline_template_as_named(self, name: str) -> bool:
        clean_name = name.strip()
        if not clean_name:
            return False
        if not self._ops:
            return False
        sp = global_assets.add_saved_pipeline(SavedPipeline(name=clean_name, ops=list(self._ops)))
        self._current_pipeline_id = sp.id
        self._refresh_pipeline_templates()
        self.assets_modified.emit()
        return True

    def _on_save_pipeline_template_as(self) -> None:
        if not self._ops:
            InfoBar.warning("提示", "当前没有可保存的处理链", parent=self, position=InfoBarPosition.TOP)
            return
        name, ok = TextInputDialog.get_text(self, "另存为 Pipeline 模板", "模板名称:", placeholder="输入模板名称")
        if not ok or not name.strip():
            return
        if self._save_pipeline_template_as_named(name):
            InfoBar.success("已保存", f"Pipeline 模板 {name.strip()} 已保存", parent=self, position=InfoBarPosition.TOP)

    def _overwrite_pipeline_template(self) -> bool:
        if not self._current_pipeline_id or not self._ops:
            return False
        updated = global_assets.update_saved_pipeline(self._current_pipeline_id, ops=list(self._ops))
        if updated:
            self.assets_modified.emit()
            self._refresh_pipeline_templates()
        return updated

    def _overwrite_current_pipeline(self) -> None:
        if not self._current_pipeline_id:
            InfoBar.warning("提示", "请先加载一个模板后再覆盖", parent=self, position=InfoBarPosition.TOP)
            return
        if self._overwrite_pipeline_template():
            InfoBar.success("已覆盖", "当前 Pipeline 模板已更新", parent=self, position=InfoBarPosition.TOP)

    # ─────────────────────────────────────────────────────────
    # 外部接口
    # ─────────────────────────────────────────────────────────

    def receive_data(self, data_type: str, obj_id: str):
        self._workspace_controller.receive_data_request(data_type, obj_id)
        if self._append_inputs_from_tree_node(data_type, obj_id):
            return
        self._refresh_tree()
        if not hasattr(self, "_src_tree") or self._src_tree is None:
            return
        for i in range(self._src_tree.topLevelItemCount()):
            root = self._src_tree.topLevelItem(i)
            for j in range(root.childCount()):
                child = root.child(j)
                d = child.data(0, Qt.ItemDataRole.UserRole)
                if d and d[1] == obj_id:
                    self._src_tree.clearSelection()
                    child.setSelected(True)
                    return

    def on_tree_node_activated(self, kind: str, node_id: str) -> None:
        handled = self._workspace_controller.handle_tree_activated(kind, node_id)
        if handled is not None:
            self.receive_data(*handled)

    def on_tree_node_selected(self, kind: str, node_id: str) -> None:
        del kind, node_id

    def load_pipeline(self, node_id: str) -> None:
        """按 pipeline_id 或旧树节点 id 加载全局 Pipeline 到当前操作链。"""
        pipeline = global_assets.get_saved_pipeline(node_id)
        if pipeline is not None:
            self._current_pipeline_id = pipeline.id
            self._refresh_pipeline_templates()
            self._load_ops_into_chain(pipeline.ops)
            return

        p = project_manager.current_project
        if p is None or p.tree is None:
            return
        node = p.tree.get_node(node_id)
        if node is None or node.kind != "pipeline":
            return
        pipeline = global_assets.get_saved_pipeline(node.pipeline_id)
        ops = pipeline.ops if pipeline is not None else project_manager.load_pipeline(node.pipeline_id)
        self._current_pipeline_id = node.pipeline_id
        self._refresh_pipeline_templates()
        self._load_ops_into_chain(ops)

    def _load_ops_into_chain(self, ops: list) -> None:
        """将 ops 列表填充到操作链 UI。"""
        for widget in self._param_widgets:
            self._param_stack.removeWidget(widget)
            widget.deleteLater()
        self._param_widgets.clear()
        self._ops.clear()
        self._op_list.clear()
        self._pipeline_selected_node_ids.clear()
        for op in ops:
            op_type = op.get("type", "")
            params = dict(op.get("params", {}))
            config_id = op.get("config_id")
            legacy_lines = normalize_extension_lines_list(params.pop("lines_list", None)) if self._is_pairing_operation(op_type, params) else []
            if legacy_lines and self._selected_inputs:
                self._pipeline_selected_node_ids = [
                    self._selected_inputs[index - 1]["node_id"]
                    for index in legacy_lines
                    if 1 <= index <= len(self._selected_inputs)
                ]
            self._ops.append({"type": op_type, "params": params, "config_id": config_id})
            if extension_registry.get_processing(op_type) is not None:
                self._processing_extension_options[op_type] = dict(params)
            self._op_list.addItem(self._op_label_for_type(op_type))
            widget = _make_param_widget(op_type, self, self._run_pipeline)
            if hasattr(widget, "set_params"):
                widget.set_params(params)
            if config_id and hasattr(widget, "load_settings_config"):
                widget.load_settings_config(config_id)
            self._param_widgets.append(widget)
            self._param_stack.addWidget(widget)
        self._sync_pipeline_lines_state()
        if self._ops:
            self._op_list.setCurrentRow(len(self._ops) - 1)
            self._on_op_selected(len(self._ops) - 1)
        else:
            self._refresh_param_stack_height()
        self._save_name_edit.setText(self._suggest_result_name())
        if self._ops:
            self._run_pipeline()

    def update_theme(self):
        self._apply_preview_host_background()
        if self._canvas is not None and self._figure is not None:
            self._draw_preview()


# ─────────────────────────────────────────────────────────────
# 参数控件
# ─────────────────────────────────────────────────────────────

class _ParamWidget(QWidget):
    def get_params(self) -> dict:
        return {}

    def set_params(self, params: dict) -> None:
        del params

    @staticmethod
    def _connect_line_edit_commit(edit: LineEdit, on_change) -> None:
        edit.editingFinished.connect(on_change)


class _JsonParam(_ParamWidget):
    def __init__(self, parent, on_change, *, description: str = "", default_params: Optional[dict] = None, fields: Optional[List[dict]] = None, entry: Optional[dict] = None, show_lines_field: bool = True):
        super().__init__(parent)
        self._page = parent if hasattr(parent, "_selected_inputs") else None
        self._fields = [dict(item) for item in (fields or []) if isinstance(item, dict)]
        if not show_lines_field:
            self._fields = [field for field in self._fields if str(field.get("key") or "") != "lines_list"]
        self._entry = dict(entry or {}) if isinstance(entry, dict) else None
        self._last_valid = dict(default_params or {})
        lv = QVBoxLayout(self)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(4)
        del description
        self._editor = ExtensionOptionsForm(self)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.setMaximumHeight(180)
        self._editor.setMaximumHeight(180)
        self._editor.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._editor.set_settings_context("processing", self._entry)
        self._editor.optionsChanged.connect(lambda _options: self._refresh_layout_height())
        self._editor.optionsCommitted.connect(lambda _options: self._handle_editor_committed(on_change))
        lv.addWidget(self._editor)
        self.set_params(self._last_valid)
        self.refresh_input_choices()

    def _refresh_layout_height(self) -> None:
        self._editor.updateGeometry()
        self.updateGeometry()
        if self._page is not None and hasattr(self._page, "_refresh_param_stack_height"):
            self._page._refresh_param_stack_height()

    def _handle_editor_committed(self, on_change) -> None:
        self._refresh_layout_height()
        on_change()

    def get_params(self) -> dict:
        try:
            data = self._editor.current_options()
        except ValueError:
            return dict(self._last_valid)
        self._last_valid = dict(data)
        return dict(self._last_valid)

    def set_params(self, params: dict) -> None:
        normalized_params = dict(params or {})
        entry_type = str((self._entry or {}).get("type") or "")
        if entry_type == "resample" and "target_line" not in normalized_params and "target_index" in normalized_params:
            normalized_params["target_line"] = normalized_params.pop("target_index")
        self._last_valid = normalized_params
        known_keys = {str(field.get("key") or "").strip() for field in self._fields}
        infer_unknown_fields = any(key not in known_keys for key in self._last_valid)
        self._editor.set_fields(self._fields, self._last_valid, infer_unknown_fields=infer_unknown_fields)
        self.refresh_input_choices()
        self._refresh_layout_height()

    def refresh_input_choices(self) -> None:
        labels = [payload.get("label", "未命名曲线") for payload in getattr(self._page, "_selected_inputs", [])]
        self._editor.set_line_candidates(labels)
        self._refresh_layout_height()

    def current_settings_config_id(self) -> Optional[str]:
        current_id = getattr(self._editor, "_current_settings_config_id", None)
        return current_id() if callable(current_id) else None

    def load_settings_config(self, config_id: str) -> None:
        entry_type = str((self._entry or {}).get("type") or "")
        if not config_id or not entry_type:
            return
        config = global_assets.get_extension_config(config_id)
        if config is None or config.extension_type != entry_type:
            return
        selected_ids = getattr(self._editor, "_selected_settings_config_ids", None)
        if isinstance(selected_ids, dict):
            selected_ids[entry_type] = config.id
        refresh_selector = getattr(self._editor, "_refresh_settings_selector", None)
        if callable(refresh_selector):
            refresh_selector()
        self._editor.set_options(dict(config.options or {}))
        self._refresh_layout_height()


def _make_param_widget(op_type: str, parent, on_change) -> _ParamWidget:
    extension = extension_registry.get_processing(op_type)
    if extension is not None:
        entry = build_extension_entry(extension)
        return _JsonParam(
            parent,
            on_change,
            description=extension.description,
            default_params=dict(entry.get("resolved_options") or {}),
            fields=list(entry.get("normalized_config_fields") or entry.get("config_fields") or []),
            entry=entry,
            show_lines_field=False,
        )
    return _ParamWidget(parent)
