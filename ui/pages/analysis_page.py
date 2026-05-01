"""分析页

布局：左侧配置（类型/已选数据/参数）| 右侧结果（图表 + 文本摘要 + 报告）
支持：曲线拟合、峰值检测、统计分析、相关性分析
新功能（v0.3）：通过共享项目树选择数据，Markdown 报告模板导出
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set

from PySide6.QtCore import QItemSelectionModel, Qt, QTimer, Signal, QStringListModel
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCompleter, QFileDialog, QHBoxLayout, QHeaderView, QListWidgetItem, QSplitter,
    QFrame, QScrollArea, QSizePolicy, QStackedWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    BodyLabel, CaptionLabel, ComboBox, EditableComboBox, FluentIcon as FIF,
    CardWidget,
    InfoBar, InfoBarPosition, PlainTextEdit, PrimaryPushButton, PushButton, TableWidget,
    TabCloseButtonDisplayMode, TabWidget, TeachingTipTailPosition, ToolButton,
)

from ui.dialogs.fluent_dialogs import SelectionDialog, TextInputDialog
from ui.dialogs.export_flow import (
    DataCreateTargetOption,
    choose_analysis_result_save_plan,
    choose_data_export_plan,
)
from models.schemas import DataSeries
from core.analysis_engine import list_report_template_placeholders, run_analysis
from app.workspaces.analysis_workspace import AnalysisWorkspaceController, AnalysisWorkspaceState
from core.report_templates import DEFAULT_REPORT_TEMPLATE
from core.shortcut_manager import ShortcutBindingSet
from ui.widgets.extension_panel import ExtensionConfigPanel
from ui.widgets.extension_options_form import ExtensionOptionsForm
from ui.widgets.focus_commit import install_click_away_focus_commit
from ui.widgets.matplotlib_preview import (
    build_preview_toolbar,
    create_navigation_toolbar,
    sync_preview_nav_toggle_states,
    toggle_preview_box_zoom_mode,
    toggle_preview_pan_mode,
    zoom_figure_axes,
)
from ui.widgets.navigation_stack import SegmentedStackWidget
from ui.widgets.onboarding import OnboardingStep, PageOnboardingController
from ui.notifications import show_error, show_warning
from ui.theme import WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_MIN_WIDTH, WORKBENCH_TOOL_PANEL_WIDTH, accent_color, apply_button_metrics, make_hint_label, make_section_label, make_hsep, placeholder_color
from .page_shell_helpers import ExtensionPanelShellMixin, sync_vertical_splitter_sizes
from core.extension_api import (
    build_extension_entry,
    extension_lines_picker_visible,
    extension_lines_number,
    extension_registry,
    reload_configured_extensions,
    normalize_extension_lines_list,
    validate_extension_lines_list,
)
from core.global_assets import global_assets
from core.project_manager import project_manager
from processing.extension_tools import line_from_xy, line_xy, normalize_line
from ui.page_view_state import AnalysisPageViewState
from .analysis_page_support import (
    Figure,
    FigureCanvas,
    HAS_MATPLOTLIB,
    _PREFERRED_ANALYSIS_ORDER,
    _SelectableResultList,
    _SelectableResultTable,
    isDarkTheme,
)


class AnalysisPage(ExtensionPanelShellMixin, QWidget):
    """数据分析页 — 通过共享项目树选择分析数据。"""

    extensions_reloaded = Signal()
    project_modified = Signal()
    assets_modified = Signal()

    # 由 main_window 框架路由的节点类型
    tree_filter_kinds: List[str] = [
        "folder", "data_file", "image_work", "global_report_template", "series", "curve",
    ]

    @property
    def _selected_inputs(self):
        return self._workspace_state.selected_inputs

    @_selected_inputs.setter
    def _selected_inputs(self, value):
        self._workspace_state.selected_inputs = value

    @property
    def _current_report_template_id(self):
        return self._workspace_state.current_report_template_id

    @_current_report_template_id.setter
    def _current_report_template_id(self, value):
        self._workspace_state.current_report_template_id = value

    @property
    def _selected_tree_node_id(self):
        return self._workspace_state.selected_tree_node_id

    @_selected_tree_node_id.setter
    def _selected_tree_node_id(self, value):
        self._workspace_state.selected_tree_node_id = value

    def __init__(self, parent=None):
        super().__init__(parent)
        self._workspace_state = AnalysisWorkspaceState()
        self._workspace_controller = AnalysisWorkspaceController(self._workspace_state)
        self._view_state = AnalysisPageViewState()
        self._result: Optional[Dict[str, Any]] = None
        self._analysis_type_labels: List[str] = []
        self._analysis_type_ids: List[str] = []
        self._analysis_label_map: Dict[str, str] = {}
        self._analysis_extension_options: Dict[str, Dict[str, Any]] = {}
        # 已选分析数据列表：List[{"kind": str, "node_id": str, "label": str}]
        self._workspace_state.selected_inputs = []
        self._workspace_state.current_report_template_id = None
        self._workspace_state.current_report_template_name = "默认模板"
        self._workspace_state.report_template_ids = [None]
        self._analysis_tab_views: Dict[str, Dict[str, Any]] = {}
        self._analysis_tab_keys: List[str] = []
        self._report_result_selectors: Dict[str, ComboBox] = {}
        self._report_result_selector_keys: Dict[str, List[Optional[str]]] = {}
        self._report_placeholder_completer: Optional[QCompleter] = None
        self._report_placeholder_search_model: Optional[QStringListModel] = None
        self._workspace_state.selected_tree_kind = None
        self._workspace_state.selected_tree_node_id = None
        self._report_placeholder_entries = list_report_template_placeholders()
        self._next_temporary_result_number = 1
        self._theme_refresh_pending = False
        self._shortcut_bindings = ShortcutBindingSet()
        self._setup_ui()
        self._apply_report_preview_theme()
        self._setup_shortcuts()
        self._click_away_focus_commit = install_click_away_focus_commit(self)
        self._onboarding_controller = PageOnboardingController(self, "analysis", self._analysis_onboarding_steps)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._sync_input_panel_splitter_sizes)
        if self._theme_refresh_pending:
            self._theme_refresh_pending = False
            QTimer.singleShot(0, self._refresh_result_views)
        self._onboarding_controller.schedule_auto_start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._view_state.input_panel_splitter_user_resized:
            QTimer.singleShot(0, self._sync_input_panel_splitter_sizes)

    def _sync_input_panel_splitter_sizes(self) -> None:
        sync_vertical_splitter_sizes(
            getattr(self, "_input_panel_splitter", None),
            user_resized=self._view_state.input_panel_splitter_user_resized,
            upper_ratio=0.4,
        )

    def _on_input_panel_splitter_moved(self, _pos: int, _index: int) -> None:
        self._view_state.input_panel_splitter_user_resized = True

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
        self._content_splitter.addWidget(self._build_left())
        self._content_splitter.addWidget(self._build_right())
        self._content_splitter.setSizes([320, 660])
        self._page_splitter.addWidget(self._content_splitter)

        self._extension_panel = ExtensionConfigPanel("分析扩展", "应用扩展", self, mode="help_only", framed=True)
        self._extension_panel.set_context("数据分析", "未选择输入")
        self._extension_panel.set_status_context("analysis", "分析扩展")
        self._extension_panel.apply_requested.connect(self._on_analysis_extension_apply)
        self._extension_panel.configs_changed.connect(self.assets_modified.emit)
        self._extension_panel.reload_requested.connect(self._reload_analysis_extensions)
        self._extension_panel.setMinimumWidth(self._view_state.extension_panel_width)
        self._extension_panel.setMaximumWidth(self._view_state.extension_panel_width)
        self._page_splitter.addWidget(self._extension_panel)
        self._page_splitter.setStretchFactor(0, 1)
        self._page_splitter.setStretchFactor(1, 0)
        self._refresh_analysis_type_choices()
        self.set_extension_panel_visible(self._view_state.extension_panel_visible)

    def _setup_shortcuts(self) -> None:
        context = Qt.ShortcutContext.WidgetWithChildrenShortcut
        self._shortcut_bindings.bind("analysis_run", self, self._run_analysis, context=context)
        self._shortcut_bindings.bind("analysis_save_result", self, self._save_result, context=context)
        self._shortcut_bindings.bind("analysis_export_result", self, self._export_result_series, context=context)
        self._shortcut_bindings.bind("analysis_clear_inputs", self, self._clear_inputs, context=context)
        self._shortcut_bindings.bind("analysis_remove_selected_input", self, self._remove_selected_inputs, context=context)
        self._shortcut_bindings.bind("analysis_generate_report", self, self._on_generate_report, context=context)
        self._shortcut_bindings.bind("analysis_save_report_template", self, self._save_report_template_as, context=context)
        self._shortcut_bindings.bind("analysis_export_report", self, self._export_report, context=context)

    def apply_shortcuts(self) -> None:
        self._shortcut_bindings.apply()

    def start_onboarding(self, force: bool = False) -> None:
        self._onboarding_controller.start(force=force)

    def _analysis_onboarding_steps(self) -> list[OnboardingStep]:
        return [
            OnboardingStep(
                lambda: self._type_combo,
                TeachingTipTailPosition.BOTTOM,
                "先选分析类型",
                "先定任务，参数区才会切到对应配置。",
            ),
            OnboardingStep(
                lambda: self._input_list,
                TeachingTipTailPosition.LEFT_BOTTOM,
                "输入统一放这里",
                "从共享树加入数据后，主输入和对比输入都在这里管理。",
            ),
            OnboardingStep(
                lambda: self._result_tabs,
                TeachingTipTailPosition.LEFT_BOTTOM,
                "结果和报告都在右侧",
                "先看结果标签，需要沉淀结论时再切到报告。",
            ),
            OnboardingStep(
                lambda: self._report_template_combo,
                TeachingTipTailPosition.BOTTOM,
                "模板在这里切换",
                "默认模板可直接渲染，自定义模板也从这里加载或更新。",
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
        panel = CardWidget(self)
        self._tool_panel = panel
        panel.setFixedWidth(WORKBENCH_TOOL_PANEL_WIDTH)
        lv = QVBoxLayout(panel)
        lv.setContentsMargins(14, 14, 14, 14)
        lv.setSpacing(8)
        analysis_type_label = make_section_label("分析类型")
        self._type_combo = ComboBox(self)
        self._type_combo.setFixedHeight(WORKBENCH_BUTTON_HEIGHT)
        self._type_combo.addItems(self._analysis_type_labels)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)

        self._input_panel_splitter = QSplitter(Qt.Orientation.Vertical, panel)
        self._input_panel_splitter.setHandleWidth(6)
        self._input_panel_splitter.setChildrenCollapsible(False)
        self._input_panel_splitter.splitterMoved.connect(self._on_input_panel_splitter_moved)
        lv.addWidget(self._input_panel_splitter, 1)

        input_section = QWidget(self._input_panel_splitter)
        input_layout = QVBoxLayout(input_section)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)

        input_layout.addWidget(make_section_label("已选择列表"))

        self._input_hint_label = make_hint_label("双击数据加入“已选择列表”；单曲线分析会处理列表中当前选中的项。")
        self._input_hint_label.hide()
        input_layout.addWidget(self._input_hint_label)

        self._selected_input_state_label = CaptionLabel("当前分析: 未选择", self)
        self._selected_input_state_label.setWordWrap(True)
        self._selected_input_state_label.setStyleSheet(f"color: {placeholder_color()};")

        self._primary_input_label = BodyLabel("主输入: 未选择")
        self._primary_input_label.setWordWrap(True)
        self._primary_input_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._primary_input_label.hide()

        self._secondary_input_label = BodyLabel("对比输入: 未使用")
        self._secondary_input_label.setWordWrap(True)
        self._secondary_input_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._secondary_input_label.hide()

        self._input_list = _SelectableResultList(self)
        self._input_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._input_list.setMinimumHeight(108)
        self._input_list.itemSelectionChanged.connect(self._on_input_list_selection_changed)
        self._input_list.currentItemChanged.connect(lambda _current, _previous: self._on_input_list_selection_changed())
        self._input_list.itemClicked.connect(self._on_input_list_item_clicked)
        input_layout.addWidget(self._input_list, 1)
        input_layout.addWidget(self._selected_input_state_label)

        clear_row = QHBoxLayout()
        self._btn_clear_inputs = PushButton(FIF.DELETE, "清除", self)
        apply_button_metrics(self._btn_clear_inputs, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        self._btn_clear_inputs.clicked.connect(self._clear_inputs)
        clear_row.addWidget(self._btn_clear_inputs)
        self._btn_remove_selected_inputs = PushButton(FIF.REMOVE, "移除选中", self)
        apply_button_metrics(self._btn_remove_selected_inputs, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        self._btn_remove_selected_inputs.clicked.connect(self._remove_selected_inputs)
        clear_row.addWidget(self._btn_remove_selected_inputs)
        self._btn_selected_up = ToolButton(FIF.UP, self)
        self._btn_selected_up.setToolTip("上移")
        self._btn_selected_up.clicked.connect(self._move_selected_inputs_up)
        self._btn_selected_up.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)
        clear_row.addWidget(self._btn_selected_up)
        self._btn_selected_down = ToolButton(FIF.DOWN, self)
        self._btn_selected_down.setToolTip("下移")
        self._btn_selected_down.clicked.connect(self._move_selected_inputs_down)
        self._btn_selected_down.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)
        clear_row.addWidget(self._btn_selected_down)
        clear_row.addStretch()
        input_layout.addLayout(clear_row)

        controls_section = QWidget(self._input_panel_splitter)
        controls_layout = QVBoxLayout(controls_section)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)

        controls_layout.addWidget(make_hsep())
        controls_layout.addWidget(analysis_type_label)
        controls_layout.addWidget(self._type_combo)

        controls_layout.addWidget(make_hsep())
        controls_layout.addWidget(make_section_label("参数"))

        self._extension_params_label = BodyLabel("", self)
        self._extension_params_label.hide()
        self._extension_params_edit = ExtensionOptionsForm(self)
        self._extension_params_edit.setMinimumHeight(120)
        self._extension_params_edit.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._extension_params_edit.optionsChanged.connect(self._on_extension_analysis_options_changed)
        controls_layout.addWidget(self._extension_params_edit, 1)
        controls_layout.addWidget(make_hsep())

        self._run_analysis_btn = PrimaryPushButton(FIF.PLAY, "运行分析")
        self._run_analysis_btn.clicked.connect(self._run_analysis)
        apply_button_metrics(self._run_analysis_btn, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        controls_layout.addWidget(self._run_analysis_btn)

        self._report_template_label = BodyLabel("当前报告模板: 默认模板")
        self._report_template_label.setWordWrap(True)
        self._report_template_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._report_template_label.hide()

        self._input_panel_splitter.setStretchFactor(0, 0)
        self._input_panel_splitter.setStretchFactor(1, 1)
        self._input_panel_splitter.setSizes([400, 600])

        self._on_type_changed(0)
        return panel

    def _build_right(self) -> QWidget:
        panel = CardWidget(self)
        rv = QVBoxLayout(panel)
        rv.setContentsMargins(14, 14, 14, 14)
        rv.setSpacing(8)
        self._result_tabs = SegmentedStackWidget(panel, fill_width=True)
        self._result_tabs.tabBar.setAddButtonVisible(False)
        self._result_tabs.tabBar.setCloseButtonDisplayMode(TabCloseButtonDisplayMode.NEVER)

        result_tab = QWidget(panel)
        result_layout = QVBoxLayout(result_tab)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(6)
        result_layout.addWidget(make_section_label("分析结果"))

        self._analysis_tabs = TabWidget(result_tab)
        self._analysis_tabs.tabBar.setAddButtonVisible(False)
        self._analysis_tabs.tabBar.setCloseButtonDisplayMode(TabCloseButtonDisplayMode.ON_HOVER)
        self._analysis_tabs.currentChanged.connect(self._on_analysis_tab_changed)
        self._analysis_tabs.tabCloseRequested.connect(self._on_analysis_tab_close_requested)
        current_view = self._create_analysis_result_view(result_tab)
        self._figure = current_view["figure"]
        self._canvas = current_view["canvas"]
        self._summary_table = current_view["summary_table"]
        self._analysis_tab_views = {"current": current_view}
        self._analysis_tab_keys = ["current"]
        self._analysis_tabs.addTab(current_view["widget"], "输入预览")
        result_layout.addWidget(self._analysis_tabs, stretch=1)

        self._analysis_status_label = CaptionLabel("调整输入或参数后，点击“运行分析”生成新的结果标签。", result_tab)
        self._analysis_status_label.setWordWrap(True)
        self._analysis_status_label.setStyleSheet(f"color: {placeholder_color()};")
        result_layout.addWidget(self._analysis_status_label)

        result_actions = QHBoxLayout()
        result_actions.setContentsMargins(0, 0, 0, 0)
        result_actions.setSpacing(6)
        self._analysis_result_actions_layout = result_actions
        self._save_result_btn = PushButton(FIF.SAVE, "保存分析结果")
        self._save_result_btn.clicked.connect(self._save_result)
        apply_button_metrics(self._save_result_btn, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        self._save_result_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        result_actions.addWidget(self._save_result_btn, 1)

        self._export_result_btn = PushButton(FIF.SHARE, "导出结果曲线")
        self._export_result_btn.clicked.connect(self._export_result_series)
        self._export_result_btn.hide()
        self._export_result_btn.setEnabled(False)
        apply_button_metrics(self._export_result_btn, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        self._export_result_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        result_actions.addWidget(self._export_result_btn, 1)

        self._generate_report_btn = PushButton(FIF.DOCUMENT, "生成报告")
        self._generate_report_btn.clicked.connect(self._on_generate_report)
        apply_button_metrics(self._generate_report_btn, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        self._generate_report_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        result_actions.addWidget(self._generate_report_btn, 1)

        result_layout.addLayout(result_actions)

        report_tab = QWidget(panel)
        report_layout = QVBoxLayout(report_tab)
        report_layout.setContentsMargins(0, 0, 0, 0)
        report_layout.setSpacing(6)
        report_layout.addWidget(make_section_label("报告模板"))

        template_row = QHBoxLayout()
        self._report_template_combo = ComboBox(panel)
        template_row.addWidget(self._report_template_combo)
        self._btn_load_report_template = ToolButton(FIF.FOLDER, panel)
        self._btn_load_report_template.setToolTip("加载选中的报告模板")
        self._btn_load_report_template.clicked.connect(self._load_selected_report_template)
        template_row.addWidget(self._btn_load_report_template)
        self._btn_update_report_template = ToolButton(FIF.SAVE, panel)
        self._btn_update_report_template.setToolTip("覆盖当前报告模板")
        self._btn_update_report_template.clicked.connect(self._save_current_report_template)
        template_row.addWidget(self._btn_update_report_template)
        self._btn_save_report_template_as = ToolButton(FIF.ADD, panel)
        self._btn_save_report_template_as.setToolTip("另存为新的报告模板")
        self._btn_save_report_template_as.clicked.connect(self._save_report_template_as)
        template_row.addWidget(self._btn_save_report_template_as)
        template_row.addStretch(1)
        report_layout.addLayout(template_row)

        placeholder_row = QHBoxLayout()
        self._report_placeholder_combo = EditableComboBox(panel)
        self._configure_report_placeholder_combo()
        self._report_placeholder_combo.currentIndexChanged.connect(self._on_report_placeholder_changed)
        placeholder_row.addWidget(self._report_placeholder_combo)
        self._btn_insert_report_placeholder = PushButton(FIF.ADD, "插入占位符", panel)
        self._btn_insert_report_placeholder.clicked.connect(self._insert_selected_report_placeholder)
        placeholder_row.addWidget(self._btn_insert_report_placeholder)
        placeholder_row.addStretch(1)
        report_layout.addLayout(placeholder_row)

        self._report_placeholder_hint = CaptionLabel("", panel)
        self._report_placeholder_hint.setWordWrap(True)
        report_layout.addWidget(self._report_placeholder_hint)

        report_layout.addWidget(make_hsep())
        report_layout.addWidget(make_section_label("结果选择"))
        self._report_result_selector_panel = QWidget(report_tab)
        self._report_result_selector_layout = QVBoxLayout(self._report_result_selector_panel)
        self._report_result_selector_layout.setContentsMargins(0, 0, 0, 0)
        self._report_result_selector_layout.setSpacing(4)
        self._report_result_selector_hint = make_hint_label("存在多个分析结果时，可按分析类型选择要渲染的结果。")
        self._report_result_selector_hint.hide()
        self._report_result_selector_layout.addWidget(self._report_result_selector_hint)
        report_layout.addWidget(self._report_result_selector_panel)

        top_row = QHBoxLayout()
        self._report_editor_title = BodyLabel("当前模板内容")
        top_row.addWidget(self._report_editor_title)
        top_row.addStretch()
        btn_render = PushButton(FIF.PLAY, "渲染", panel)
        btn_render.clicked.connect(self._render_report_preview)
        top_row.addWidget(btn_render)
        btn_export = PushButton(FIF.SHARE, "导出 Markdown", panel)
        btn_export.clicked.connect(self._export_report)
        top_row.addWidget(btn_export)
        report_layout.addLayout(top_row)

        self._report_editor = PlainTextEdit(panel)
        self._report_editor.setPlaceholderText("在此编辑报告 Markdown 模板…")
        report_layout.addWidget(self._report_editor, stretch=1)

        report_layout.addWidget(make_hsep())
        report_layout.addWidget(make_section_label("渲染预览"))
        self._report_preview = PlainTextEdit(panel)
        self._report_preview.setReadOnly(True)
        report_layout.addWidget(self._report_preview, stretch=1)
        self._apply_report_preview_theme()

        self._refresh_report_placeholder_choices()
        self._sync_report_combo_widths()

        self._result_tabs.addTab(result_tab, "分析结果")
        self._result_tabs.addTab(report_tab, "生成报告")
        rv.addWidget(self._result_tabs, stretch=1)
        self._refresh_report_template_combo()
        self._sync_report_editor_from_template()
        self._refresh_report_result_selectors()
        return panel

    def _create_analysis_result_view(self, parent: QWidget) -> Dict[str, Any]:
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        figure = None
        canvas = None
        preview_nav_toolbar = None
        preview_buttons = None
        view_ref: Dict[str, Any] = {}
        plot_widget = QWidget(widget)
        plot_layout = QVBoxLayout(plot_widget)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_layout.setSpacing(0)
        if HAS_MATPLOTLIB:
            figure = Figure(figsize=(6, 4))
            canvas = FigureCanvas(figure)
            canvas.setMinimumHeight(300)
            self._apply_result_canvas_background(canvas)
            preview_nav_toolbar = create_navigation_toolbar(
                canvas,
                plot_widget,
                sync_callback=lambda ref=view_ref: self._sync_analysis_preview_nav_toggle_states(ref.get("view")),
            )
            preview_toolbar, preview_buttons = build_preview_toolbar(
                plot_widget,
                button_size=WORKBENCH_BUTTON_HEIGHT,
                reset_callback=lambda _checked=False, ref=view_ref: self._reset_analysis_preview_view(ref.get("view")),
                zoom_in_callback=lambda _checked=False, ref=view_ref: self._zoom_analysis_preview_axes(ref.get("view"), 0.8),
                zoom_out_callback=lambda _checked=False, ref=view_ref: self._zoom_analysis_preview_axes(ref.get("view"), 1.25),
                pan_toggle_callback=lambda checked, ref=view_ref: self._toggle_analysis_preview_pan_mode(ref.get("view"), checked),
                box_zoom_toggle_callback=lambda checked, ref=view_ref: self._toggle_analysis_preview_box_zoom_mode(ref.get("view"), checked),
            )
            plot_layout.addLayout(preview_toolbar)
            plot_layout.addWidget(canvas, stretch=1)
        else:
            plot_layout.addWidget(BodyLabel("需要 matplotlib"), stretch=1)

        plot_stack = QStackedWidget(widget)
        plot_stack.setMinimumHeight(300)
        plot_stack.addWidget(plot_widget)

        empty_preview_widget = QWidget(plot_stack)
        empty_preview_layout = QVBoxLayout(empty_preview_widget)
        empty_preview_layout.setContentsMargins(0, 0, 0, 0)
        empty_preview_layout.setSpacing(0)
        empty_preview_layout.addStretch(1)
        empty_preview_label = BodyLabel("选择曲线后将在此预览\n双击左侧数据加入已选择列表", empty_preview_widget)
        empty_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_preview_label.setWordWrap(True)
        empty_preview_label.setStyleSheet(f"color: {placeholder_color()}; font-size: 15px;")
        empty_preview_layout.addWidget(empty_preview_label, 0, Qt.AlignmentFlag.AlignCenter)
        empty_preview_layout.addStretch(1)
        plot_stack.addWidget(empty_preview_widget)
        plot_stack.setCurrentWidget(empty_preview_widget)
        layout.addWidget(plot_stack, stretch=2)

        layout.addWidget(make_hsep())
        layout.addWidget(make_section_label("摘要"))
        summary_stack = QStackedWidget(widget)
        summary_stack.setMinimumHeight(280)
        summary_table = _SelectableResultTable(widget)
        self._configure_result_table(summary_table, ["数据类型", "结果"])
        summary_stack.addWidget(summary_table)

        details_scroll = QScrollArea(summary_stack)
        details_scroll.setFrameShape(QFrame.Shape.NoFrame)
        details_scroll.setWidgetResizable(True)
        details_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        details_container = QWidget(details_scroll)
        details_layout = QVBoxLayout(details_container)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(8)
        details_scroll.setWidget(details_container)
        summary_stack.addWidget(details_scroll)
        layout.addWidget(summary_stack, stretch=2)

        view = {
            "widget": widget,
            "figure": figure,
            "canvas": canvas,
            "preview_nav_toolbar": preview_nav_toolbar,
            "preview_fit_btn": preview_buttons.fit if preview_buttons is not None else None,
            "preview_zoom_in_btn": preview_buttons.zoom_in if preview_buttons is not None else None,
            "preview_zoom_out_btn": preview_buttons.zoom_out if preview_buttons is not None else None,
            "preview_pan_btn": preview_buttons.pan if preview_buttons is not None else None,
            "preview_box_zoom_btn": preview_buttons.box_zoom if preview_buttons is not None else None,
            "plot_stack": plot_stack,
            "plot_widget": plot_widget,
            "empty_preview_widget": empty_preview_widget,
            "empty_preview_label": empty_preview_label,
            "summary_stack": summary_stack,
            "summary_table": summary_table,
            "details_scroll": details_scroll,
            "details_container": details_container,
            "details_layout": details_layout,
            "detail_summary_table": None,
            "detail_tables": [],
            "detail_text_widgets": [],
            "normalized_result": None,
            "result": None,
            "analysis_type": None,
            "selected": [],
            "inputs": [],
            "params": {},
            "analysis_name": "当前结果",
        }
        view_ref["view"] = view
        self._set_summary_rows(summary_table, [("状态", "（运行分析后显示结果）")])
        self._sync_analysis_preview_nav_toggle_states(view)
        return view

    def _sync_report_combo_widths(self) -> None:
        if not hasattr(self, "_report_template_combo") or not hasattr(self, "_report_placeholder_combo"):
            return
        shared_width = max(
            self._report_template_combo.sizeHint().width(),
            self._report_placeholder_combo.sizeHint().width(),
            280,
        )
        shared_width = min(shared_width, 360)
        self._report_template_combo.setFixedWidth(shared_width)
        self._report_placeholder_combo.setFixedWidth(shared_width)

    @staticmethod
    def _configure_result_table(table: TableWidget, headers: List[str]) -> None:
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        table.setAlternatingRowColors(True)
        table.setWordWrap(True)
        table.setTextElideMode(Qt.TextElideMode.ElideNone)
        table.verticalHeader().setDefaultSectionSize(32)

    def _set_summary_rows(self, table: TableWidget, rows: List[tuple[str, str]]) -> None:
        table.setRowCount(len(rows))
        for row_idx, (label, value) in enumerate(rows):
            table.setItem(row_idx, 0, QTableWidgetItem(label))
            table.setItem(row_idx, 1, QTableWidgetItem(value))
        table.resizeRowsToContents()

    @staticmethod
    def _format_summary_value(value: Any) -> str:
        if value in (None, ""):
            return ""
        if isinstance(value, float):
            return f"{value:.6g}"
        return str(value)

    def _flatten_json_summary(self, rows: List[tuple[str, str]], value: Any, prefix: str = "") -> None:
        if isinstance(value, dict):
            if not value:
                rows.append((prefix or "结果", "{}"))
                return
            for key, item in value.items():
                if str(key).startswith("_"):
                    continue
                label = f"{prefix}.{key}" if prefix else str(key)
                self._flatten_json_summary(rows, item, label)
            return
        if isinstance(value, list):
            if not value:
                rows.append((prefix or "结果", "[]"))
                return
            if all(not isinstance(item, (dict, list)) for item in value):
                if len(value) > 12:
                    preview = ", ".join(self._format_summary_value(item) for item in value[:5])
                    rows.append((prefix or "结果", f"{preview} ...（共 {len(value)} 项）"))
                    return
                rows.append((prefix or "结果", ", ".join(self._format_summary_value(item) for item in value)))
                return
            for index, item in enumerate(value):
                label = f"{prefix}[{index}]" if prefix else f"[{index}]"
                self._flatten_json_summary(rows, item, label)
            return
        rows.append((prefix or "结果", self._format_summary_value(value)))

    def _json_summary_rows(self, value: Any) -> List[tuple[str, str]]:
        rows: List[tuple[str, str]] = []
        self._flatten_json_summary(rows, value)
        return rows or [("结果", self._format_summary_value(value))]

    def _set_result_table_rows(self, table: TableWidget, rows: List[List[Any]]) -> None:
        table.setRowCount(len(rows))
        for row_idx, values in enumerate(rows):
            for col_idx, value in enumerate(values):
                table.setItem(row_idx, col_idx, QTableWidgetItem(self._format_summary_value(value)))
        table.resizeRowsToContents()

    @staticmethod
    def _clear_layout_widgets(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _normalized_summary_items(self, value: Any) -> List[tuple[str, str]]:
        if isinstance(value, list):
            rows: List[tuple[str, str]] = []
            for item in value:
                if isinstance(item, dict):
                    label = str(item.get("label") or item.get("key") or "结果")
                    rows.append((label, self._format_summary_value(item.get("value"))))
                    continue
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    rows.append((str(item[0]), self._format_summary_value(item[1])))
            if rows:
                return rows
        return []

    def _normalized_table_sections(self, result: dict) -> List[Dict[str, Any]]:
        sections: List[Dict[str, Any]] = []
        raw_sections = list(result.get("tables") or result.get("table_sections") or [])
        for index, item in enumerate(raw_sections):
            if not isinstance(item, dict):
                continue
            headers = list(item.get("headers") or item.get("columns") or [])
            rows = list(item.get("rows") or [])
            if not headers or not rows:
                continue
            sections.append({
                "title": str(item.get("title") or f"结果表 {index + 1}"),
                "headers": [str(header) for header in headers],
                "rows": [list(row) if isinstance(row, (list, tuple)) else [row] for row in rows],
            })
        return sections

    def _normalized_text_sections(self, result: dict) -> List[Dict[str, str]]:
        sections: List[Dict[str, str]] = []
        raw_sections = list(result.get("texts") or result.get("text_sections") or [])
        for index, item in enumerate(raw_sections):
            if isinstance(item, str):
                clean_content = item.strip()
                if clean_content:
                    sections.append({"title": f"说明 {index + 1}", "content": clean_content})
                continue
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or item.get("text") or item.get("markdown") or "").strip()
            if not content:
                continue
            sections.append({
                "title": str(item.get("title") or f"说明 {index + 1}"),
                "content": content,
            })
        inline_text = str(result.get("text") or result.get("markdown") or "").strip()
        if inline_text:
            sections.append({"title": "说明", "content": inline_text})
        return sections

    def _normalize_analysis_output(self, t: str, selected: list, r: dict) -> Dict[str, Any]:
        del selected
        plot = {
            "series": [],
            "x_label": str(r.get("x_label") or "").strip() or None,
            "y_label": str(r.get("y_label") or "").strip() or None,
            "title": str(r.get("plot_title") or "").strip() or None,
        }
        normalized = {
            "analysis_type": t,
            "summary_items": [],
            "plot": plot,
            "tables": self._normalized_table_sections(r),
            "texts": self._normalized_text_sections(r),
            "preferred_summary_widget": "summary",
        }

        result_lines = self._analysis_result_lines(r)
        line_lookup = {item["line_name"]: item["line"] for item in result_lines}
        custom_series = list(r.get("_plot_series", []) or r.get("plot_series", []) or [])
        for index, series in enumerate(custom_series):
            if not isinstance(series, dict):
                continue
            resolved_line = self._resolve_analysis_series_line(series, line_lookup)
            if resolved_line is None:
                continue
            xs, ys = line_xy(resolved_line)
            plot["series"].append(
                {
                    "kind": str(series.get("kind") or series.get("mode") or series.get("plot_type") or "line"),
                    "x": xs,
                    "y": ys,
                    "label": str(series.get("name") or series.get("line") or f"结果曲线 {index + 1}"),
                    "color": str(series.get("color") or "#0078D4"),
                    "line_width": float(series.get("line_width", 1.6)),
                    "line_style": str(series.get("line_style") or "-"),
                    "marker": str(series.get("marker") or ""),
                    "size": float(series.get("size") or 24),
                    "alpha": float(series.get("alpha") or 1.0),
                }
            )

        if not plot["series"]:
            for index, item in enumerate(result_lines, start=1):
                xs, ys = line_xy(item["line"])
                plot["series"].append(
                    {
                        "kind": "line",
                        "x": xs,
                        "y": ys,
                        "label": str(item.get("line_name") or f"结果曲线 {index}"),
                        "color": "#0078D4",
                        "line_width": 1.6,
                        "line_style": "-",
                        "marker": "",
                        "size": 24.0,
                        "alpha": 1.0,
                    }
                )

        structured_keys = {
            "summary_items",
            "lines",
            "plot_series",
            "_plot_series",
            "tables",
            "table_sections",
            "texts",
            "text_sections",
            "text",
            "markdown",
            "plot_title",
            "x_label",
            "y_label",
        }
        summary_payload = {
            key: value
            for key, value in r.items()
            if key not in structured_keys and not str(key).startswith("_")
        }
        normalized["summary_items"] = (
            self._normalized_summary_items(r.get("summary_items"))
            or (self._json_summary_rows(summary_payload) if summary_payload else [])
        )
        if normalized["tables"] or normalized["texts"]:
            normalized["preferred_summary_widget"] = "details"
        return normalized

    @staticmethod
    def _analysis_result_lines(result: Dict[str, Any]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for index, item in enumerate(list(result.get("lines") or []), start=1):
            if not isinstance(item, dict):
                continue
            line_name = str(item.get("line_name") or item.get("name") or f"结果曲线 {index}").strip()
            if not line_name:
                continue
            try:
                line_value = normalize_line(item.get("line"))
            except ValueError:
                continue
            items.append({"line_name": line_name, "line": line_value})
        return items

    @staticmethod
    def _resolve_analysis_series_line(series: Dict[str, Any], line_lookup: Dict[str, Any]) -> Any:
        line_value = series.get("line")
        if isinstance(line_value, str):
            return line_lookup.get(line_value)
        if line_value in (None, ""):
            return None
        try:
            return normalize_line(line_value)
        except ValueError:
            return None

    def _populate_detail_summary_view(self, view: Dict[str, Any], normalized: Dict[str, Any]) -> None:
        details_layout = view.get("details_layout")
        if details_layout is None:
            return
        self._clear_layout_widgets(details_layout)
        view["detail_summary_table"] = None
        view["detail_tables"] = []
        view["detail_text_widgets"] = []

        summary_items = list(normalized.get("summary_items") or [])
        if summary_items:
            details_layout.addWidget(make_section_label("摘要信息", view["details_container"]))
            summary_table = _SelectableResultTable(view["details_container"])
            self._configure_result_table(summary_table, ["项目", "结果"])
            self._set_summary_rows(summary_table, summary_items)
            details_layout.addWidget(summary_table)
            view["detail_summary_table"] = summary_table

        for section in list(normalized.get("tables") or []):
            details_layout.addWidget(make_section_label(str(section.get("title") or "结果表"), view["details_container"]))
            table = _SelectableResultTable(view["details_container"])
            headers = [str(header) for header in list(section.get("headers") or [])]
            self._configure_result_table(table, headers)
            self._set_result_table_rows(table, [list(row) for row in list(section.get("rows") or [])])
            details_layout.addWidget(table)
            view["detail_tables"].append(table)

        for section in list(normalized.get("texts") or []):
            details_layout.addWidget(make_section_label(str(section.get("title") or "说明"), view["details_container"]))
            text_label = BodyLabel(str(section.get("content") or ""), view["details_container"])
            text_label.setWordWrap(True)
            text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            details_layout.addWidget(text_label)
            view["detail_text_widgets"].append(text_label)

        details_layout.addStretch(1)

    def _analysis_type_label(self, analysis_type: str) -> str:
        return self._analysis_label_map.get(analysis_type, analysis_type or "分析结果")

    @staticmethod
    def _analysis_entry_sort_key(entry: dict) -> tuple[int, int, str, str]:
        type_id = str(entry.get("type") or "")
        if type_id in _PREFERRED_ANALYSIS_ORDER:
            return (0, _PREFERRED_ANALYSIS_ORDER.index(type_id), "", type_id)
        return (1, len(_PREFERRED_ANALYSIS_ORDER), str(entry.get("name") or type_id).casefold(), type_id)

    def _analysis_extension_entries(self) -> List[dict]:
        entries: List[dict] = []
        for extension in extension_registry.list_analysis():
            entry = build_extension_entry(extension)
            if not entry.get("listed", True):
                continue
            entries.append(entry)
        return sorted(entries, key=self._analysis_entry_sort_key)

    def _parse_extension_analysis_options_text(self, text: Optional[str] = None) -> Dict[str, Any]:
        if text is None:
            return self._extension_params_edit.current_options()
        raw_text = text
        clean_text = str(raw_text or "").strip()
        if not clean_text:
            return {}
        try:
            data = json.loads(clean_text)
        except Exception as exc:
            raise ValueError(f"扩展参数不是合法 JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("扩展参数必须是 JSON 对象")
        return data

    def _default_extension_analysis_options(self, analysis_type: str) -> Dict[str, Any]:
        extension = extension_registry.get_analysis(analysis_type)
        if extension is None:
            return {}
        entry = build_extension_entry(extension)
        return dict(entry.get("resolved_options") or {})

    def _extension_analysis_fields(self, analysis_type: str) -> List[dict]:
        extension = extension_registry.get_analysis(analysis_type)
        if extension is None:
            return []
        entry = build_extension_entry(extension)
        return [
            dict(item)
            for item in (entry.get("normalized_config_fields") or entry.get("config_fields") or [])
            if isinstance(item, dict)
        ]

    def _current_extension_analysis_options(self, analysis_type: Optional[str] = None, *, raise_on_error: bool = False) -> Dict[str, Any]:
        type_id = analysis_type or self._current_analysis_type()
        if extension_registry.get_analysis(type_id) is None:
            return {}
        lines_number = extension_lines_number(extension_registry.get_analysis(type_id))
        fallback_options = dict(self._analysis_extension_options.get(type_id, {}))
        if self._extension_uses_current_input(lines_number):
            fallback_options.pop("lines_list", None)
        if not fallback_options:
            fallback_options = self._default_extension_analysis_options(type_id)
        if self._extension_uses_current_input(lines_number):
            fallback_options.pop("lines_list", None)
        if type_id == self._current_analysis_type():
            try:
                options = self._parse_extension_analysis_options_text()
            except ValueError:
                if raise_on_error:
                    raise
                return dict(fallback_options)
            if self._extension_uses_current_input(lines_number):
                options.pop("lines_list", None)
            if not options and fallback_options:
                self._analysis_extension_options[type_id] = dict(fallback_options)
                return dict(fallback_options)
            self._analysis_extension_options[type_id] = dict(options)
            return dict(options)
        return dict(fallback_options)

    def _sync_extension_params_editor(self, analysis_type: Optional[str] = None) -> None:
        type_id = analysis_type or self._current_analysis_type()
        options: Dict[str, Any] = {}
        fields: List[dict] = []
        infer_unknown_fields = False
        entry: Optional[dict] = None
        if extension_registry.get_analysis(type_id) is not None:
            options = dict(self._analysis_extension_options.get(type_id, {}))
            if not options:
                options = self._default_extension_analysis_options(type_id)
                if options:
                    self._analysis_extension_options[type_id] = dict(options)
            fields = self._extension_analysis_fields(type_id)
            entry = next((item for item in self._analysis_extension_entries() if str(item.get("type") or "") == type_id), None)
            known_keys = {str(field.get("key") or "").strip() for field in fields}
            infer_unknown_fields = any(key not in known_keys for key in options)
        self._extension_params_edit.set_line_candidates([payload.get("label", "未命名曲线") for payload in self._selected_inputs])
        self._extension_params_edit.set_settings_context("analysis", entry)
        self._extension_params_edit.blockSignals(True)
        self._extension_params_edit.set_fields(fields, dict(options), infer_unknown_fields=infer_unknown_fields)
        self._extension_params_edit.blockSignals(False)

    def _refresh_analysis_type_choices(self) -> None:
        current_type = self._current_analysis_type() if hasattr(self, "_type_combo") else None
        entries = self._analysis_extension_entries()
        if not entries:
            entries = [
                {"type": "curve_fit", "name": "曲线拟合"},
                {"type": "peak_detect", "name": "峰值检测"},
                {"type": "statistics", "name": "统计分析"},
                {"type": "correlation", "name": "相关性分析"},
                {"type": "error_compare", "name": "误差对比"},
            ]
        self._analysis_type_labels = [str(entry.get("name") or entry.get("type") or "分析") for entry in entries]
        self._analysis_type_ids = [str(entry.get("type") or "") for entry in entries]
        self._analysis_label_map = {
            str(entry.get("type") or ""): str(entry.get("name") or entry.get("type") or "分析")
            for entry in entries
            if str(entry.get("type") or "")
        }
        self._type_combo.blockSignals(True)
        self._type_combo.clear()
        self._type_combo.addItems(self._analysis_type_labels)
        if current_type in self._analysis_type_ids:
            self._type_combo.setCurrentIndex(self._analysis_type_ids.index(current_type))
        else:
            self._type_combo.setCurrentIndex(0)
        self._type_combo.blockSignals(False)
        self._extension_panel.set_entries(
            self._analysis_extension_entries(),
            saved_options=self._analysis_extension_options,
            current_type=current_type if extension_registry.get_analysis(current_type or "") else None,
        )
        self._on_type_changed(self._type_combo.currentIndex())
        self._refresh_report_placeholder_choices()

    def refresh_analysis_type_choices(self) -> None:
        self._refresh_analysis_type_choices()

    def _on_analysis_extension_apply(self, type_id: str, options: Dict[str, Any]) -> None:
        self._analysis_extension_options[type_id] = dict(options)
        if type_id in self._analysis_type_ids:
            self._type_combo.setCurrentIndex(self._analysis_type_ids.index(type_id))
        self._sync_extension_params_editor(type_id)
        InfoBar.success("已应用", f"当前分析类型已切换为 {self._analysis_type_label(type_id)}", parent=self, position=InfoBarPosition.TOP)

    def _reload_analysis_extensions(self) -> None:
        report = reload_configured_extensions()
        self._refresh_analysis_type_choices()
        self._refresh_report_placeholder_choices()
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

    def _report_result_candidates_by_type(self) -> Dict[str, List[Dict[str, Any]]]:
        candidates: Dict[str, List[Dict[str, Any]]] = {}
        seen_keys: Set[str] = set()
        active_key = self._analysis_tab_key_for_index(self._analysis_tabs.currentIndex())
        for key in self._analysis_tab_keys:
            if str(key).startswith("temp:") and key != active_key:
                continue
            view = self._analysis_tab_views.get(key)
            if view is None:
                continue
            result = view.get("result")
            if not isinstance(result, dict) or not result:
                continue
            analysis_type = str(view.get("analysis_type") or result.get("analysis_type") or "")
            if not analysis_type:
                continue
            seen_keys.add(str(key))
            candidates.setdefault(analysis_type, []).append({
                "key": key,
                "title": view.get("analysis_name") or ("当前结果" if key == "current" else "分析结果"),
                "result": dict(result),
            })
        for analysis_type, items in self._saved_report_result_candidates_by_type().items():
            bucket = candidates.setdefault(analysis_type, [])
            for item in items:
                item_key = str(item.get("key") or "")
                if item_key in seen_keys:
                    continue
                seen_keys.add(item_key)
                bucket.append(item)
        return candidates

    def _saved_report_result_candidates_by_type(self) -> Dict[str, List[Dict[str, Any]]]:
        candidates: Dict[str, List[Dict[str, Any]]] = {}
        project = project_manager.current_project
        if project is None:
            return candidates
        payloads = self._analysis_input_payloads()
        if len(payloads) != 1:
            return candidates
        primary = payloads[0]
        series = project_manager.get_series_from_node(primary["kind"], primary["node_id"])
        if series is None:
            return candidates
        for analysis in project.analyses:
            if series.id not in list(analysis.input_series_ids or []):
                continue
            result = self._rehydrate_saved_result_payload(analysis)
            analysis_type = str(analysis.analysis_type or result.get("analysis_type") or "")
            if not analysis_type:
                continue
            candidates.setdefault(analysis_type, []).append({
                "key": analysis.id,
                "title": analysis.name or self._analysis_type_label(analysis_type),
                "result": result,
            })
        return candidates

    def _clear_report_result_selectors(self) -> None:
        if not hasattr(self, "_report_result_selector_layout"):
            return
        while self._report_result_selector_layout.count() > 1:
            item = self._report_result_selector_layout.takeAt(1)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._report_result_selectors.clear()
        self._report_result_selector_keys.clear()

    def _refresh_report_result_selectors(self) -> None:
        if not hasattr(self, "_report_result_selector_layout"):
            return
        candidates = self._report_result_candidates_by_type()
        total_results = sum(len(items) for items in candidates.values())
        self._clear_report_result_selectors()
        self._report_result_selector_panel.setVisible(total_results > 1)
        if total_results <= 1:
            return
        for analysis_type in self._analysis_type_ids:
            items = candidates.get(analysis_type, [])
            if not items:
                continue
            row = QWidget(self._report_result_selector_panel)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            row_layout.addWidget(BodyLabel(f"{self._analysis_type_label(analysis_type)}:"), 0)
            combo = ComboBox(row)
            combo.addItem("不包含")
            keys: List[Optional[str]] = [None]
            for item in items:
                combo.addItem(item["title"])
                keys.append(item["key"])
            previous_keys = self._report_result_selector_keys.get(analysis_type, [])
            previous_combo = self._report_result_selectors.get(analysis_type)
            previous_key = None
            if previous_combo is not None and previous_keys:
                previous_index = previous_combo.currentIndex()
                if 0 <= previous_index < len(previous_keys):
                    previous_key = previous_keys[previous_index]
            combo_index = keys.index(previous_key) if previous_key in keys else (1 if len(keys) > 1 else 0)
            combo.setCurrentIndex(combo_index)
            combo.currentIndexChanged.connect(self._on_report_result_selection_changed)
            row_layout.addWidget(combo, 1)
            self._report_result_selector_layout.addWidget(row)
            self._report_result_selectors[analysis_type] = combo
            self._report_result_selector_keys[analysis_type] = keys

    def _on_report_result_selection_changed(self, _index: int) -> None:
        self._refresh_report_placeholder_choices()
        self._render_report_preview()

    def _selected_report_results(self) -> List[Dict[str, Any]]:
        candidates = self._report_result_candidates_by_type()
        total_results = sum(len(items) for items in candidates.values())
        if total_results <= 1:
            for analysis_type in self._analysis_type_ids:
                items = candidates.get(analysis_type, [])
                if items:
                    return items[:1]
            return []

        selected_items: List[Dict[str, Any]] = []
        for analysis_type in self._analysis_type_ids:
            items = candidates.get(analysis_type, [])
            if not items:
                continue
            combo = self._report_result_selectors.get(analysis_type)
            keys = self._report_result_selector_keys.get(analysis_type, [])
            selected_key = None
            if combo is not None and 0 <= combo.currentIndex() < len(keys):
                selected_key = keys[combo.currentIndex()]
            if selected_key is None:
                continue
            selected_item = next((item for item in items if item["key"] == selected_key), None)
            if selected_item is not None:
                selected_items.append(selected_item)
        return selected_items

    def _render_summary_view(self, view: Dict[str, Any], t: str, r: dict) -> None:
        normalized = view.get("normalized_result")
        if not isinstance(normalized, dict):
            normalized = self._normalize_analysis_output(t, view.get("selected") or [], r)
            view["normalized_result"] = normalized
        summary_stack = view.get("summary_stack")
        if summary_stack is None:
            self._set_summary_rows(view["summary_table"], list(normalized.get("summary_items") or []))
            return
        if normalized.get("tables") or normalized.get("texts"):
            self._populate_detail_summary_view(view, normalized)
            summary_stack.setCurrentWidget(view["details_scroll"])
            return
        summary_stack.setCurrentWidget(view["summary_table"])
        self._set_summary_rows(view["summary_table"], list(normalized.get("summary_items") or []))

    def _analysis_tab_key_for_index(self, index: int) -> Optional[str]:
        if 0 <= index < len(self._analysis_tab_keys):
            return self._analysis_tab_keys[index]
        return None

    def _analysis_view_for_key(self, key: str) -> Optional[Dict[str, Any]]:
        return self._analysis_tab_views.get(key)

    def _active_analysis_view(self) -> Optional[Dict[str, Any]]:
        key = self._analysis_tab_key_for_index(self._analysis_tabs.currentIndex())
        if not key:
            return None
        return self._analysis_view_for_key(key)

    def _sync_state_from_analysis_view(self, view: Dict[str, Any]) -> None:
        self._figure = view.get("figure")
        self._canvas = view.get("canvas")
        self._summary_table = view.get("summary_table")
        result = view.get("result") if isinstance(view.get("result"), dict) else {}
        current_view = self._analysis_tab_views.get("current") if hasattr(self, "_analysis_tab_views") else None
        is_current_view = view is current_view
        params = view.get("params") if isinstance(view.get("params"), dict) else {}
        analysis_type = view.get("analysis_type") or result.get("analysis_type", "curve_fit")
        if is_current_view:
            input_refs = params.get("input_refs") if isinstance(params, dict) else None
            active_input_refs = params.get("active_input_refs") if isinstance(params, dict) else None
            if analysis_type in self._analysis_type_ids:
                self._type_combo.setCurrentIndex(self._analysis_type_ids.index(analysis_type))
            self._restore_analysis_params(view.get("params") or {})
            source_inputs = input_refs if isinstance(input_refs, list) else (view.get("inputs") or [])
            self._selected_inputs = [dict(item) for item in source_inputs if isinstance(item, dict)]
            active_inputs = active_input_refs if isinstance(active_input_refs, list) else (view.get("inputs") or [])
            selected_ids = {
                str(item.get("node_id"))
                for item in active_inputs
                if isinstance(item, dict) and item.get("node_id")
            }
            current_node_id = next(
                (
                    str(item.get("node_id"))
                    for item in active_inputs
                    if isinstance(item, dict) and item.get("node_id")
                ),
                None,
            )
            self._rebuild_input_list(selected_ids, current_node_id)
        self._result = dict(result) if isinstance(result, dict) else None
        if isinstance(result, dict) and result:
            self._set_analysis_status(f"当前结果: {view.get('analysis_name') or self._analysis_type_label(analysis_type)}")
        else:
            self._set_analysis_status("调整输入或参数后，点击“运行分析”生成新的结果标签。")
        self._refresh_result_action_buttons()
        self._render_report_preview()

    def _refresh_result_action_buttons(self) -> None:
        if not hasattr(self, "_export_result_btn") or self._export_result_btn is None:
            return
        result = self._current_analysis_result_payload()
        has_lines = bool(result and self._analysis_result_lines(result))
        self._export_result_btn.setVisible(has_lines)
        self._export_result_btn.setEnabled(has_lines)

    def _on_analysis_tab_changed(self, index: int) -> None:
        key = self._analysis_tab_key_for_index(index)
        if not key:
            return
        view = self._analysis_view_for_key(key)
        if view is None:
            return
        self._sync_state_from_analysis_view(view)

    def _on_analysis_tab_close_requested(self, index: int) -> None:
        if index <= 0:
            return
        tab_key = self._analysis_tab_key_for_index(index)
        if not tab_key or tab_key == "current":
            return
        was_current = self._analysis_tabs.currentIndex() == index
        view = self._analysis_tab_views.pop(tab_key, None)
        self._analysis_tab_keys.pop(index)
        self._analysis_tabs.removeTab(index)
        if view is not None and view.get("widget") is not None:
            view["widget"].deleteLater()
        if was_current:
            new_index = self._analysis_tabs.currentIndex()
            new_key = self._analysis_tab_key_for_index(new_index)
            new_view = self._analysis_view_for_key(new_key) if new_key else None
            if new_view is not None:
                self._sync_state_from_analysis_view(new_view)
        self._refresh_report_result_selectors()

    def _set_analysis_status(self, message: str) -> None:
        if hasattr(self, "_analysis_status_label"):
            self._analysis_status_label.setText(message)

    def _current_analysis_view(self) -> Optional[Dict[str, Any]]:
        if not hasattr(self, "_analysis_tabs") or not self._analysis_tab_keys:
            return self._analysis_tab_views.get("current") if hasattr(self, "_analysis_tab_views") else None
        index = self._analysis_tabs.currentIndex()
        if 0 <= index < len(self._analysis_tab_keys):
            return self._analysis_tab_views.get(self._analysis_tab_keys[index])
        return self._analysis_tab_views.get("current")

    def _set_analysis_plot_surface(self, view: Optional[Dict[str, Any]], *, show_plot: bool) -> None:
        if not isinstance(view, dict):
            return
        plot_stack = view.get("plot_stack")
        plot_widget = view.get("plot_widget")
        empty_preview_widget = view.get("empty_preview_widget")
        if plot_stack is None or plot_widget is None or empty_preview_widget is None:
            return
        plot_stack.setCurrentWidget(plot_widget if show_plot else empty_preview_widget)

    # ─────────────────────────────────────────────────────────
    # 共享树接口
    # ─────────────────────────────────────────────────────────

    def on_tree_node_selected(self, kind: str, node_id: str) -> None:
        """单击选中节点（只更新高亮，不加入分析列表）。"""
        self._workspace_controller.handle_tree_selected(kind, node_id)

    def on_tree_node_activated(self, kind: str, node_id: str) -> None:
        """双击树节点 → 加入分析输入列表。"""
        handled = self._workspace_controller.handle_tree_activated(kind, node_id)
        if handled is None:
            return
        kind, node_id = handled
        if kind == "global_report_template":
            self.load_report_template(node_id)
            return
        if kind not in ("series", "curve", "data_file", "image_work"):
            return
        if not self._append_inputs_from_tree_node(kind, node_id):
            return
        self._sync_related_analysis_tabs()

    def _get_node_label(self, kind: str, node_id: str) -> str:
        p = project_manager.current_project
        if p is None:
            return node_id[:16]
        if kind == "series":
            s = p.find_series(node_id)
            return s.name if s else node_id[:16]
        if kind == "curve":
            c = project_manager.get_curve(node_id)
            return c.name if c else node_id[:16]
        if kind == "data_file":
            node = project_manager.get_node_by_id(node_id)
            if node and node.kind == "data_file":
                df = p.find_data_file(node.data_file_id)
                return df.name if df else node_id[:16]
        if kind == "image_work":
            img = project_manager.get_image(node_id)
            if img:
                return img.name
            node = project_manager.get_node_by_id(node_id)
            if node and node.kind == "image_work":
                img = project_manager.get_image(node.image_work_id)
                return img.name if img else node_id[:16]
        return node_id[:16]

    def _resolve_input_payloads(self, kind: str, node_id: str) -> List[dict]:
        if kind == "data_file":
            container_name = project_manager.format_tree_path_label(node_id, separator="/", omit_root_group=True) or "数据文件"
            payloads: List[dict] = []
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
            payloads: List[dict] = []
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

    def _selected_input_node_ids(self) -> List[str]:
        node_ids: List[str] = []
        for item in self._input_list.selectedItems():
            payload = item.data(Qt.ItemDataRole.UserRole)
            if payload and payload.get("node_id"):
                node_ids.append(str(payload["node_id"]))
        return node_ids

    def _current_selected_input_node_id(self) -> Optional[str]:
        item = self._input_list.currentItem() if hasattr(self, "_input_list") else None
        if item is None:
            return None
        payload = item.data(Qt.ItemDataRole.UserRole)
        if payload and payload.get("node_id"):
            return str(payload["node_id"])
        return None

    def _active_input_payloads(self, *, prefer_current: bool = False) -> List[dict]:
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
        current_payload = next((payload for payload in active_payloads if payload.get("node_id") == current_node_id), None)
        if current_payload is None:
            return active_payloads
        return [current_payload] + [payload for payload in active_payloads if payload.get("node_id") != current_node_id]

    def _append_inputs_from_tree_node(self, kind: str, node_id: str) -> bool:
        payloads = self._resolve_input_payloads(kind, node_id)
        if not payloads:
            return False

        selected_ids = set(self._selected_input_node_ids())
        for payload in payloads:
            if any(item["node_id"] == payload["node_id"] for item in self._selected_inputs):
                selected_ids.add(payload["node_id"])
                continue
            self._selected_inputs.append(payload)
            selected_ids.add(payload["node_id"])
        self._rebuild_input_list(selected_ids)
        return True

    def _current_input_node_id(self) -> Optional[str]:
        if not hasattr(self, "_input_list"):
            return None
        item = self._input_list.currentItem()
        if item is None:
            return None
        payload = item.data(Qt.ItemDataRole.UserRole)
        if not payload:
            return None
        node_id = payload.get("node_id")
        return str(node_id) if node_id else None

    def _clear_inputs(self):
        self._selected_inputs.clear()
        self._rebuild_input_list(set())
        self._sync_related_analysis_tabs()

    def _remove_selected_inputs(self):
        to_remove = set(self._selected_input_node_ids())
        if not to_remove:
            return
        self._selected_inputs = [payload for payload in self._selected_inputs if payload["node_id"] not in to_remove]
        self._rebuild_input_list(set())
        self._sync_related_analysis_tabs()

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
        self._rebuild_input_list(selected_set)
        self._sync_related_analysis_tabs()

    def _rebuild_input_list(self, selected_ids: Optional[Set[str]] = None, current_node_id: Optional[str] = None) -> None:
        if selected_ids is None:
            selected_ids = set(self._selected_input_node_ids())
        if current_node_id is None:
            current_node_id = self._current_input_node_id()
        self._input_list.blockSignals(True)
        self._input_list.clear()
        current_item: Optional[QListWidgetItem] = None
        for payload in self._selected_inputs:
            item = QListWidgetItem(payload["label"])
            item.setData(Qt.ItemDataRole.UserRole, {"kind": payload["kind"], "node_id": payload["node_id"]})
            item.setToolTip(payload["label"])
            self._input_list.addItem(item)
            if payload["node_id"] in selected_ids:
                item.setSelected(True)
            if payload["node_id"] == current_node_id:
                current_item = item
        if current_item is not None:
            current_item.setSelected(True)
            self._input_list.setCurrentItem(current_item, QItemSelectionModel.SelectionFlag.NoUpdate)
        self._input_list.blockSignals(False)
        self._sync_input_role_labels()
        if extension_registry.get_analysis(self._current_analysis_type()) is not None:
            self._sync_extension_params_editor(self._current_analysis_type())

    def _current_selected_input_payload(self) -> Optional[Dict[str, Any]]:
        current_item = self._input_list.currentItem() if hasattr(self, "_input_list") else None
        if current_item is not None:
            payload = current_item.data(Qt.ItemDataRole.UserRole)
            if isinstance(payload, dict) and payload.get("node_id"):
                current_payload = dict(payload)
                current_payload["label"] = str(current_payload.get("label") or current_item.text() or "未命名曲线")
                return current_payload
        selected_ids = set(self._selected_input_node_ids())
        if selected_ids:
            for payload in self._selected_inputs:
                if payload.get("node_id") in selected_ids:
                    return payload
        return self._selected_inputs[0] if self._selected_inputs else None

    def _sync_input_role_labels(self, options: Optional[Dict[str, Any]] = None) -> None:
        del options
        primary = self._selected_inputs[0]["label"] if self._selected_inputs else "未选择"
        secondary = self._selected_inputs[1]["label"] if len(self._selected_inputs) > 1 else "未使用"
        self._primary_input_label.setText(f"主输入: {primary}")
        self._secondary_input_label.setText(f"对比输入: {secondary}")
        current_payload = self._current_selected_input_payload()
        if current_payload is None:
            self._selected_input_state_label.setText("当前分析: 未选择")
        else:
            self._selected_input_state_label.setText(f"当前分析: {current_payload.get('label', '未命名曲线')}")
        if hasattr(self, "_extension_panel"):
            if not self._selected_inputs:
                target = "未选择输入"
            elif len(self._selected_inputs) == 1:
                target = primary
            else:
                target = f"{primary} 等 {len(self._selected_inputs)} 条输入"
            self._extension_panel.set_context("数据分析", target)

    def _on_input_list_selection_changed(self) -> None:
        self._result = None
        self._sync_input_role_labels()
        self._sync_related_analysis_tabs()

    def _on_input_list_item_clicked(self, item: Optional[QListWidgetItem]) -> None:
        if item is None:
            return
        if self._input_list.currentItem() is not item:
            self._input_list.setCurrentItem(item)
            return
        if not item.isSelected():
            item.setSelected(True)
        self._on_input_list_selection_changed()

    def _on_extension_analysis_options_changed(self, options: Dict[str, Any]) -> None:
        type_id = self._current_analysis_type()
        if extension_registry.get_analysis(type_id) is None:
            return
        self._result = None
        self._analysis_extension_options[type_id] = dict(options or {})
        self._sync_input_role_labels()
        self._refresh_current_analysis_preview()

    def _current_analysis_type(self) -> str:
        idx = self._type_combo.currentIndex()
        return self._analysis_type_ids[idx] if 0 <= idx < len(self._analysis_type_ids) else "curve_fit"

    @staticmethod
    def _line_number_spec(value: Any, default: int = 1) -> int:
        try:
            return int(value)
        except Exception:
            return default

    @staticmethod
    def _extension_uses_current_input(lines_number: Optional[tuple[int, int]]) -> bool:
        if lines_number is None:
            return True
        _lower, upper = lines_number
        return upper in {0, 1}

    def _resolve_extension_input_payloads(self, analysis_type: str, options: Optional[Dict[str, Any]] = None) -> List[dict]:
        extension = extension_registry.get_analysis(analysis_type)
        lines_number = extension_lines_number(extension) if extension is not None else None
        config = dict(options or self._current_extension_analysis_options(analysis_type, raise_on_error=False))
        if lines_number is None:
            active = self._active_input_payloads(prefer_current=True)
            return active[:1] if active else list(self._selected_inputs[:1])

        picker_visible = extension_lines_picker_visible(lines_number)

        def _implicit_payloads() -> List[dict]:
            payloads = self._active_input_payloads(prefer_current=True) or list(self._selected_inputs)
            upper = lines_number[1]
            if upper == 0:
                return []
            if upper != -1:
                return payloads[:upper]
            return payloads

        try:
            explicit_lines = normalize_extension_lines_list(config.get("lines_list")) if "lines_list" in config else []
        except ValueError:
            explicit_lines = []

        if "lines_list" in config:
            if explicit_lines:
                payloads = []
                for index in explicit_lines:
                    try:
                        offset = int(index) - 1
                    except Exception:
                        continue
                    if 0 <= offset < len(self._selected_inputs):
                        payloads.append(self._selected_inputs[offset])
            elif picker_visible:
                payloads = []
            else:
                payloads = _implicit_payloads()
        elif picker_visible:
            payloads = []
        else:
            payloads = _implicit_payloads()
        return payloads

    def _payload_indices(self, payloads: List[dict]) -> List[int]:
        indices: List[int] = []
        node_ids = [payload.get("node_id") for payload in self._selected_inputs]
        for payload in payloads:
            node_id = payload.get("node_id")
            if node_id not in node_ids:
                continue
            indices.append(node_ids.index(node_id) + 1)
        return indices

    def _effective_extension_analysis_options(self, analysis_type: str, options: Dict[str, Any]) -> tuple[List[dict], Dict[str, Any]]:
        payloads = self._resolve_extension_input_payloads(analysis_type, options)
        effective_options = dict(options or {})
        extension = extension_registry.get_analysis(analysis_type)
        lines_number = extension_lines_number(extension) if extension is not None else None
        if payloads:
            effective_options["lines_list"] = self._payload_indices(payloads)
        if lines_number is not None:
            validate_extension_lines_list(effective_options["lines_list"], lines_number, present=True)
        return payloads, effective_options

    def _analysis_input_payloads(self, analysis_type: Optional[str] = None, options: Optional[Dict[str, Any]] = None) -> List[dict]:
        type_id = analysis_type or self._current_analysis_type()
        extension = extension_registry.get_analysis(type_id)
        if extension is not None:
            return self._resolve_extension_input_payloads(type_id, options)
        if type_id in {"curve_fit", "peak_detect", "statistics"}:
            active = self._active_input_payloads(prefer_current=True)
            return active[:1] if active else list(self._selected_inputs[:1])
        return self._resolve_extension_input_payloads(type_id, options)

    # ─────────────────────────────────────────────────────────
    # 类型切换
    # ─────────────────────────────────────────────────────────

    def _on_type_changed(self, idx: int):
        t = self._analysis_type_ids[idx] if 0 <= idx < len(self._analysis_type_ids) else "curve_fit"
        self._result = None
        uses_extension_form = extension_registry.get_analysis(t) is not None
        self._extension_params_label.setVisible(False)
        self._extension_params_edit.setVisible(uses_extension_form)
        if uses_extension_form:
            self._sync_extension_params_editor(t)
        if uses_extension_form:
            self._input_hint_label.setText("双击数据加入“已选择列表”；多曲线扩展必须在“选择曲线”中显式勾选输入。")
        else:
            self._input_hint_label.setText("双击数据加入“已选择列表”；单曲线分析会处理列表中当前选中的项。")
        self._sync_input_role_labels()
        self._refresh_current_analysis_preview()
        if hasattr(self, "_extension_panel"):
            self._extension_panel.set_entries(
                self._analysis_extension_entries(),
                saved_options=self._analysis_extension_options,
                current_type=t if extension_registry.get_analysis(t) else None,
            )

    # ─────────────────────────────────────────────────────────
    # 获取分析数据
    # ─────────────────────────────────────────────────────────

    def _get_selected_data(self) -> List[tuple]:
        return self._get_data_for_inputs(self._analysis_input_payloads())

    def _get_data_for_inputs(self, inputs: List[dict]) -> List[tuple]:
        """返回 (xs, ys, name) 列表。"""
        result = []
        for inp in inputs:
            kind = inp["kind"]
            node_id = inp["node_id"]
            series = project_manager.get_series_from_node(kind, node_id)
            if series and series.x:
                result.append((list(series.x), list(series.y), series.name))
        return result

    # ─────────────────────────────────────────────────────────
    # 运行分析
    # ─────────────────────────────────────────────────────────

    def _run_analysis(self):
        analysis_type = self._current_analysis_type()
        extension_options: Optional[Dict[str, Any]] = None
        effective_extension_options: Optional[Dict[str, Any]] = None
        override_cursor = False
        run_started = False
        try:
            input_payloads: List[dict]
            if extension_registry.get_analysis(analysis_type) is not None:
                extension_options = self._current_extension_analysis_options(analysis_type, raise_on_error=True)
                input_payloads, effective_extension_options = self._effective_extension_analysis_options(analysis_type, extension_options)
                selected = self._get_data_for_inputs(input_payloads)
            else:
                input_payloads = self._analysis_input_payloads(analysis_type)
                selected = self._get_data_for_inputs(input_payloads)
            if not selected:
                show_warning(self, "提示", "请先从项目树双击选择数据")
                return

            t = analysis_type
            self._set_analysis_status("正在运行分析，结果生成后会创建新的临时标签。")
            self._run_analysis_btn.setEnabled(False)
            run_started = True
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            override_cursor = True
            inputs = [{"x": xs, "y": ys, "name": name} for xs, ys, name in selected]
            self._result = run_analysis(t, inputs, effective_extension_options)
            self._show_result(t, selected)
        except Exception as e:
            message = show_error(self, "分析失败", e)
            preview_view = self._analysis_tab_views.get("current")
            if preview_view is not None and preview_view.get("summary_table") is not None:
                self._set_summary_rows(preview_view["summary_table"], [("错误", message)])
            self._set_analysis_status(f"分析失败: {message}")
        finally:
            if override_cursor:
                QApplication.restoreOverrideCursor()
            if run_started:
                self._run_analysis_btn.setEnabled(True)

    # ─────────────────────────────────────────────────────────
    # 结果显示
    # ─────────────────────────────────────────────────────────

    def _show_result(self, t: str, selected: list):
        r = self._result
        if r is None:
            return
        tab_number = self._next_temporary_result_number
        self._next_temporary_result_number += 1
        tab_key = f"temp:{tab_number}"
        title = f"{self._analysis_type_label(t)} #{tab_number}"
        view = self._ensure_analysis_result_tab(tab_key, title)
        view["result"] = dict(r)
        view["analysis_type"] = t
        view["selected"] = list(selected)
        view["inputs"] = [dict(item) for item in self._selected_inputs]
        view["params"] = self._current_analysis_params()
        view["analysis_name"] = title
        view["temporary"] = True
        self._render_result_view(view, t, selected, r)
        self._analysis_tabs.setCurrentIndex(self._analysis_tab_keys.index(tab_key))
        self._sync_state_from_analysis_view(view)
        self._set_analysis_status(f"分析完成，已生成临时结果标签“{title}”。")
        self._refresh_report_placeholder_choices()

    def _render_result_view(self, view: Dict[str, Any], t: str, selected: list, r: dict) -> None:
        normalized = self._normalize_analysis_output(t, selected, r)
        view["normalized_result"] = normalized
        self._set_analysis_plot_surface(view, show_plot=True)
        self._draw_result(t, selected, r, figure=view.get("figure"), canvas=view.get("canvas"), normalized=normalized)
        self._render_summary_view(view, t, r)
        self._refresh_report_result_selectors()

    def _refresh_current_analysis_preview(self) -> None:
        view = self._analysis_tab_views.get("current")
        if view is None:
            return
        analysis_type = self._current_analysis_type()
        payloads = self._analysis_input_payloads(analysis_type)
        selected = self._get_data_for_inputs(payloads)
        params: Dict[str, Any] = {
            "analysis_type": analysis_type,
            "input_refs": [dict(item) for item in self._selected_inputs],
            "active_input_refs": [dict(item) for item in payloads],
        }
        if extension_registry.get_analysis(analysis_type) is not None:
            params["extension_options"] = self._current_extension_analysis_options(analysis_type, raise_on_error=False)
        view["result"] = None
        view["analysis_type"] = analysis_type
        view["selected"] = list(selected)
        view["inputs"] = [dict(item) for item in payloads]
        view["params"] = params
        view["analysis_name"] = "当前结果"
        if selected:
            self._set_analysis_plot_surface(view, show_plot=True)
            self._draw_result(analysis_type, selected, {"_preview_only": True}, figure=view.get("figure"), canvas=view.get("canvas"))
        else:
            self._set_analysis_plot_surface(view, show_plot=False)
        summary_rows = [("状态", "已更新输入预览，运行分析后显示结果。")]
        if payloads:
            summary_rows.append(("已选曲线", "；".join(str(item.get("label") or "") for item in payloads)))
        else:
            summary_rows.append(("已选曲线", "当前未显式选中可用于分析的曲线。"))
        summary_rows.append(("分析类型", analysis_type))
        self._set_summary_rows(view["summary_table"], summary_rows)
        view["summary_stack"].setCurrentWidget(view["summary_table"])
        if self._analysis_tabs.currentIndex() == 0:
            self._figure = view.get("figure")
            self._canvas = view.get("canvas")
            self._summary_table = view.get("summary_table")
            self._result = None
            self._set_analysis_status("调整输入或参数后，点击“运行分析”生成新的结果标签。")
            self._render_report_preview()

    def _draw_result(self, t: str, selected: list, r: dict, figure=None, canvas=None, normalized: Optional[Dict[str, Any]] = None):
        figure = self._figure if figure is None else figure
        canvas = self._canvas if canvas is None else canvas
        if not HAS_MATPLOTLIB or figure is None or canvas is None:
            return
        figure.clear()
        ax = figure.add_subplot(111)
        dark = isDarkTheme()
        bg = "#1e1e1e" if dark else "#ffffff"
        fg = "#cccccc" if dark else "#222222"
        gc = "#444444" if dark else "#dddddd"
        self._apply_result_canvas_background(canvas)
        figure.patch.set_facecolor(bg)
        ax.set_facecolor(bg)
        ax.tick_params(colors=fg, labelcolor=fg)
        for sp in ax.spines.values():
            sp.set_edgecolor(fg)
        ax.grid(True, color=gc, linestyle="--", linewidth=0.5, alpha=0.6)

        if r.get("_preview_only"):
            palette = ["#0078D4", "#D13438", "#107C10", "#8764B8"]
            if selected:
                for index, (xs, ys, name) in enumerate(selected):
                    ax.plot(xs, ys, color=palette[index % len(palette)], linewidth=1.4, label=name)
                ax.set_title("待分析曲线预览", color=fg)
                ax.legend(facecolor=bg, edgecolor=fg, labelcolor=fg, fontsize=8)
            else:
                ax.text(0.5, 0.5, "选择曲线后将在此预览", ha="center", va="center", color=fg, transform=ax.transAxes)
                ax.set_xticks([])
                ax.set_yticks([])
            canvas.draw()
            return

        normalized = normalized if isinstance(normalized, dict) else self._normalize_analysis_output(t, selected, r)
        plot = dict(normalized.get("plot") or {})
        plotted = False
        has_labels = False
        palette = ["#0078D4", "#D13438", "#107C10", "#8764B8"]
        for index, series in enumerate(list(plot.get("series") or [])):
            xs = list(series.get("x", []) or [])
            ys = list(series.get("y", []) or [])
            if not xs or not ys or len(xs) != len(ys):
                continue
            label = str(series.get("label") or "").strip()
            if label:
                has_labels = True
            color = str(series.get("color") or palette[index % len(palette)])
            kind = str(series.get("kind") or "line").strip().lower()
            alpha = float(series.get("alpha", 1.0))
            if kind in {"scatter", "markers"}:
                ax.scatter(
                    xs,
                    ys,
                    s=float(series.get("size", 24)),
                    color=color,
                    alpha=alpha,
                    marker=str(series.get("marker") or ("o" if kind == "scatter" else "o")),
                    label=label or None,
                    zorder=5 if kind == "markers" else 3,
                )
                plotted = True
                continue
            ax.plot(
                xs,
                ys,
                color=color,
                linewidth=float(series.get("line_width", 1.6)),
                linestyle=str(series.get("line_style") or "-"),
                marker=str(series.get("marker") or ""),
                alpha=alpha,
                label=label or None,
            )
            plotted = True

        if plot.get("x_label"):
            ax.set_xlabel(str(plot.get("x_label")), color=fg)
        if plot.get("y_label"):
            ax.set_ylabel(str(plot.get("y_label")), color=fg)
        if plot.get("title"):
            ax.set_title(str(plot.get("title")), color=fg)
        if plotted and has_labels:
            ax.legend(facecolor=bg, edgecolor=fg, labelcolor=fg, fontsize=8)
        if not plotted:
            ax.text(0.5, 0.5, "当前结果没有可绘制的曲线", ha="center", va="center", color=fg, transform=ax.transAxes)
            ax.set_xticks([])
            ax.set_yticks([])

        canvas.draw()
        self._sync_analysis_preview_nav_toggle_states(self._analysis_view_for_canvas(canvas))

    def _apply_result_canvas_background(self, canvas=None) -> None:
        canvas = self._canvas if canvas is None else canvas
        if canvas is None:
            return
        background = "#1e1e1e" if isDarkTheme() else "#ffffff"
        canvas.setStyleSheet(f"background: {background};")
        figure = getattr(canvas, "figure", None)
        if figure is not None:
            figure.patch.set_facecolor(background)
            for axis in figure.axes:
                axis.set_facecolor(background)
        try:
            canvas.draw_idle()
        except Exception:
            pass

    def _analysis_view_for_canvas(self, canvas) -> Optional[Dict[str, Any]]:
        if canvas is None:
            return None
        for view in getattr(self, "_analysis_tab_views", {}).values():
            if view.get("canvas") is canvas:
                return view
        return None

    def _sync_analysis_preview_nav_toggle_states(self, view: Optional[Dict[str, Any]] = None) -> None:
        if view is None:
            return
        sync_preview_nav_toggle_states(
            view.get("preview_nav_toolbar"),
            view.get("preview_pan_btn"),
            view.get("preview_box_zoom_btn"),
        )

    def _toggle_analysis_preview_pan_mode(self, view: Optional[Dict[str, Any]], checked: bool) -> None:
        if view is None:
            return
        toggle_preview_pan_mode(
            view.get("preview_nav_toolbar"),
            view.get("preview_pan_btn"),
            view.get("preview_box_zoom_btn"),
            checked,
        )

    def _toggle_analysis_preview_box_zoom_mode(self, view: Optional[Dict[str, Any]], checked: bool) -> None:
        if view is None:
            return
        toggle_preview_box_zoom_mode(
            view.get("preview_nav_toolbar"),
            view.get("preview_pan_btn"),
            view.get("preview_box_zoom_btn"),
            checked,
        )

    def _zoom_analysis_preview_axes(self, view: Optional[Dict[str, Any]], factor: float) -> None:
        if view is None:
            return
        zoom_figure_axes(
            view.get("figure"),
            view.get("canvas"),
            factor,
            redraw_callback=lambda current_view=view: self._redraw_analysis_preview_view(current_view),
        )

    def _reset_analysis_preview_view(self, view: Optional[Dict[str, Any]]) -> None:
        self._redraw_analysis_preview_view(view)

    def _redraw_analysis_preview_view(self, view: Optional[Dict[str, Any]]) -> None:
        if view is None:
            return
        analysis_type = str(view.get("analysis_type") or self._current_analysis_type())
        selected = list(view.get("selected") or [])
        result = view.get("result")
        normalized = view.get("normalized_result")
        if result is not None:
            self._draw_result(
                analysis_type,
                selected,
                result,
                figure=view.get("figure"),
                canvas=view.get("canvas"),
                normalized=normalized,
            )
            return
        if selected:
            self._draw_result(
                analysis_type,
                selected,
                {"_preview_only": True},
                figure=view.get("figure"),
                canvas=view.get("canvas"),
            )
            return
        self._sync_analysis_preview_nav_toggle_states(view)

    def _write_summary(self, analysis_type: str, result: Dict[str, Any]) -> None:
        view = self._active_analysis_view() or self._analysis_tab_views.get("current")
        table = self._summary_table if self._summary_table is not None else (view.get("summary_table") if isinstance(view, dict) else None)
        if table is None:
            return

        normalized = self._normalize_analysis_output(analysis_type, view.get("selected") if isinstance(view, dict) else [], dict(result or {}))
        self._set_summary_rows(table, list(normalized.get("summary_items") or []))
        if isinstance(view, dict) and view.get("summary_stack") is not None and view.get("summary_table") is not None:
            view["summary_stack"].setCurrentWidget(view["summary_table"])

    # ─────────────────────────────────────────────────────────
    # 保存分析结果
    # ─────────────────────────────────────────────────────────

    def _default_analysis_result_name(self) -> str:
        active_view = self._active_analysis_view()
        active_result = dict(active_view.get("result") or {}) if isinstance(active_view, dict) else dict(self._result or {})
        type_label = self._analysis_type_label(self._current_analysis_type())
        source_name = str(active_result.get("source_name") or "").strip()
        if source_name:
            return f"{source_name}_{type_label}"
        return f"{type_label}结果"

    def _save_result(self):
        active_view = self._active_analysis_view()
        active_result = dict(active_view.get("result") or {}) if isinstance(active_view, dict) else None
        if not active_result:
            InfoBar.warning("提示", "请先运行分析", parent=self,
                            position=InfoBarPosition.TOP)
            return
        if project_manager.current_project is None:
            return
        from models.schemas import AnalysisResult

        default_name = self._default_analysis_result_name()
        save_plan = choose_analysis_result_save_plan(
            self,
            title="保存分析结果",
            default_result_name=default_name,
            preferred_target_node_id=self._preferred_analysis_result_target_node_id(),
        )
        if save_plan is None:
            return
        clean_name = save_plan.result_name.strip()
        if not clean_name:
            return

        input_series_ids = []
        for item in list(active_view.get("inputs") or []) if isinstance(active_view, dict) else []:
            series = project_manager.get_series_from_node(item["kind"], item["node_id"])
            if series is not None:
                input_series_ids.append(series.id)
        ar = AnalysisResult(
            name=clean_name,
            analysis_type=active_result.get("analysis_type", "analysis"),
            input_series_ids=input_series_ids,
            params=dict(active_view.get("params") or {}) if isinstance(active_view, dict) else self._current_analysis_params(),
            summary=dict(active_result),
        )
        if not project_manager.add_analysis(ar, parent_id=save_plan.target_parent_id):
            InfoBar.error("保存失败", "未能保存分析结果到目标位置", parent=self, position=InfoBarPosition.TOP)
            return
        if isinstance(active_view, dict):
            active_view["saved_analysis_id"] = ar.id
        self._refresh_report_result_selectors()
        self.project_modified.emit()
        self._set_analysis_status(f"已保存分析结果“{clean_name}”。")
        InfoBar.success("已保存", "分析结果已保存至项目", parent=self,
                        position=InfoBarPosition.TOP)

    def _preferred_analysis_result_target_node_id(self) -> Optional[str]:
        if self._selected_tree_node_id:
            return project_manager.get_analysis_result_target_folder_id(self._selected_tree_node_id)
        return project_manager.get_analysis_result_target_folder_id(None)

    def _ensure_analysis_result_folder(self) -> Optional[str]:
        dataset_root = project_manager.find_folder_by_group_type("datasets")
        if dataset_root is None:
            return None
        for node in project_manager.get_children(dataset_root.id):
            if node.kind == "folder" and node.name == "分析结果":
                return node.id
        folder = project_manager.add_folder("分析结果", parent_id=dataset_root.id)
        return folder.id if folder is not None else None

    def _current_analysis_result_payload(self) -> Dict[str, Any]:
        result = dict(self._result or {}) if isinstance(self._result, dict) else {}
        if result:
            return result
        active_view = self._active_analysis_view()
        if isinstance(active_view, dict):
            return dict(active_view.get("result") or {})
        return {}

    def _analysis_output_series_options(self) -> List[Dict[str, Any]]:
        result = self._current_analysis_result_payload()
        result_lines = self._analysis_result_lines(result)
        if not result_lines:
            return []

        labels_by_line: Dict[str, str] = {}
        custom_series = list(result.get("_plot_series", []) or result.get("plot_series", []) or [])
        for series in custom_series:
            if not isinstance(series, dict):
                continue
            line_name = series.get("line")
            if not isinstance(line_name, str) or not line_name.strip():
                continue
            label = str(series.get("name") or line_name).strip() or line_name
            labels_by_line.setdefault(line_name.strip(), label)

        options: List[Dict[str, Any]] = []
        used_labels: Set[str] = set()
        for index, item in enumerate(result_lines, start=1):
            line_name = str(item.get("line_name") or f"结果曲线 {index}")
            label = labels_by_line.get(line_name, line_name)
            if label in used_labels:
                label = f"{label}（{line_name}）" if label != line_name else f"{label} #{index}"
            used_labels.add(label)
            xs, ys = line_xy(item["line"])
            options.append(
                {
                    "line_name": line_name,
                    "label": label,
                    "series": DataSeries(name=line_name, x=xs, y=ys, source="computed"),
                }
            )
        return options

    def _build_analysis_output_series(self, export_name: str) -> Optional[DataSeries]:
        options = self._analysis_output_series_options()
        if not options:
            return None
        first_series = options[0]["series"]
        return DataSeries(
            name=export_name,
            x=list(first_series.x),
            y=list(first_series.y),
            source="computed",
        )

    def _analysis_export_create_targets(self) -> List[DataCreateTargetOption]:
        return [
            DataCreateTargetOption(
                label="新建数据文件 / 数据集 / 分析结果（若不存在则创建）",
                ensure_parent_id=self._ensure_analysis_result_folder,
            )
        ]

    def _preferred_analysis_export_target_node_id(self) -> Optional[str]:
        return next(
            (item["node_id"] for item in self._selected_inputs if item.get("kind") == "data_file"),
            getattr(project_manager.find_folder_by_group_type("datasets"), "id", None),
        )

    def _export_current_series(self, series, *, title: str) -> bool:
        from models.schemas import DataFile

        export_plan = choose_data_export_plan(
            self,
            title=title,
            default_export_name=series.name,
            default_file_name=f"{series.name}.analysis",
            preferred_target_node_id=self._preferred_analysis_export_target_node_id(),
            file_suffix=".analysis",
            create_target_options=self._analysis_export_create_targets(),
        )
        if export_plan is None:
            return False
        series.name = export_plan.export_name.strip() or series.name
        if export_plan.target_data_file_id:
            if not project_manager.add_series_to_data_file(export_plan.target_data_file_id, series):
                InfoBar.error("导出失败", "未能追加数据到目标数据文件", parent=self, position=InfoBarPosition.TOP)
                return False
        else:
            data_file = DataFile(name=export_plan.new_data_file_name or f"{series.name}.analysis", series=[series])
            if project_manager.add_data_file(data_file, parent_id=export_plan.new_parent_id) is None:
                InfoBar.error("导出失败", "未能创建目标数据文件", parent=self, position=InfoBarPosition.TOP)
                return False
        self.project_modified.emit()
        InfoBar.success("已导出", f"{series.name} 已导出到数据集", parent=self, position=InfoBarPosition.TOP)
        return True

    def _export_result_series(self) -> None:
        result = self._current_analysis_result_payload()
        if not result:
            InfoBar.warning("提示", "请先运行分析", parent=self, position=InfoBarPosition.TOP)
            return
        options = self._analysis_output_series_options()
        if not options:
            InfoBar.warning("提示", "当前分析结果没有可导出的数据曲线", parent=self, position=InfoBarPosition.TOP)
            return
        selected_option = options[0]
        if len(options) > 1:
            labels = [str(item.get("label") or item.get("line_name") or "结果曲线") for item in options]
            choice, accepted = SelectionDialog.get_item(
                self,
                "导出结果曲线",
                "选择要导出的结果曲线",
                labels,
                current_text=labels[0],
            )
            if not accepted:
                return
            selected_option = next(
                (item for item in options if str(item.get("label") or "") == choice),
                options[0],
            )
        selected_series = selected_option["series"]
        series = DataSeries(
            name=str(selected_series.name or self._default_analysis_result_name()),
            x=list(selected_series.x),
            y=list(selected_series.y),
            source="computed",
        )
        self._export_current_series(series, title="导出分析结果")

    # ─────────────────────────────────────────────────────────
    # 报告模板
    # ─────────────────────────────────────────────────────────

    def _on_generate_report(self):
        self._result_tabs.setCurrentIndex(1)
        self._render_report_preview()

    def _current_report_template_content(self) -> str:
        if self._current_report_template_id:
            template = project_manager.get_report_template(self._current_report_template_id)
            if template is not None:
                return template.content
        return DEFAULT_REPORT_TEMPLATE

    def _report_template_choices(self) -> List[tuple[str, Optional[str]]]:
        choices: List[tuple[str, Optional[str]]] = [("默认模板", None)]
        for template in global_assets.list_report_templates(include_builtin=False):
            choices.append((template.name or "未命名模板", template.id))
        return choices

    def _refresh_report_template_combo(self, select_template_id: Optional[str] = None) -> None:
        choices = self._report_template_choices()
        target_template_id = select_template_id if select_template_id is not None else self._current_report_template_id
        self._report_template_combo.blockSignals(True)
        self._report_template_combo.clear()
        self._report_template_ids = []
        selected_index = 0
        for index, (label, template_id) in enumerate(choices):
            self._report_template_combo.addItem(label)
            self._report_template_ids.append(template_id)
            if template_id == target_template_id:
                selected_index = index
        self._report_template_combo.setCurrentIndex(selected_index)
        self._report_template_combo.blockSignals(False)
        self._btn_update_report_template.setEnabled(self._current_report_template_id is not None)

    def _selected_report_template_id(self) -> Optional[str]:
        idx = self._report_template_combo.currentIndex()
        if idx < 0 or idx >= len(self._report_template_ids):
            return None
        return self._report_template_ids[idx]

    def _load_selected_report_template(self) -> None:
        self._load_report_template_by_id(self._selected_report_template_id(), announce=True)

    def _load_report_template_by_id(self, template_id: Optional[str], announce: bool = False) -> bool:
        content = DEFAULT_REPORT_TEMPLATE
        template_name = "默认模板"
        current_template_id = None
        if template_id:
            template = project_manager.get_report_template(template_id)
            if template is None:
                return False
            content = template.content
            template_name = template.name or "默认模板"
            current_template_id = None if template.is_builtin else template.id
        self._current_report_template_id = current_template_id
        self._current_report_template_name = template_name
        self._report_template_label.setText(f"当前报告模板: {self._current_report_template_name}")
        self._refresh_report_template_combo(current_template_id)
        self._report_editor.setPlainText(content)
        self._render_report_preview()
        if announce:
            InfoBar.success(
                "已应用模板",
                f"当前报告模板已切换为 {self._current_report_template_name}",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2500,
            )
        return True

    def _selected_report_placeholder_entry(self) -> Optional[Dict[str, str]]:
        index = self._report_placeholder_combo.currentIndex()
        if 0 <= index < len(self._report_placeholder_entries):
            return self._report_placeholder_entries[index]
        return None

    def _configure_report_placeholder_combo(self) -> None:
        search_model = QStringListModel(self)
        completer = QCompleter(self._report_placeholder_combo)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setModel(search_model)
        completer.activated.connect(lambda value: self._select_report_placeholder_entry_by_text(str(value)))
        self._report_placeholder_combo.setCompleter(completer)
        self._report_placeholder_completer = completer
        self._report_placeholder_search_model = search_model
        self._report_placeholder_combo.setPlaceholderText("输入通用项、工具名或占位符筛选")

    @staticmethod
    def _report_placeholder_group(entry: Dict[str, Any]) -> str:
        return str(entry.get("group") or "通用").strip() or "通用"

    def _report_placeholder_group_prefix(self, entry: Dict[str, Any]) -> str:
        return f"[{self._report_placeholder_group(entry)}]"

    def _report_placeholder_display_text(self, entry: Dict[str, Any]) -> str:
        label = str(entry.get("label") or entry.get("token") or "占位符").strip() or "占位符"
        return f"{self._report_placeholder_group_prefix(entry)}{label} · {entry['token']}"

    def _refresh_report_placeholder_completer(self) -> None:
        if self._report_placeholder_search_model is None:
            return
        self._report_placeholder_search_model.setStringList(
            [self._report_placeholder_display_text(entry) for entry in self._report_placeholder_entries]
        )

    def _select_report_placeholder_entry_by_text(self, text: str) -> None:
        clean_text = str(text or "").strip()
        if not clean_text:
            return
        target_index = next(
            (
                index
                for index, entry in enumerate(self._report_placeholder_entries)
                if self._report_placeholder_display_text(entry) == clean_text or entry.get("token") == clean_text
            ),
            -1,
        )
        if target_index < 0:
            target_index = next(
                (
                    index
                    for index, entry in enumerate(self._report_placeholder_entries)
                    if clean_text.casefold() in self._report_placeholder_display_text(entry).casefold()
                ),
                -1,
            )
        if target_index >= 0 and self._report_placeholder_combo.currentIndex() != target_index:
            self._report_placeholder_combo.setCurrentIndex(target_index)

    def _select_report_placeholder_entry_from_editor_text(self) -> None:
        if not hasattr(self, "_report_placeholder_combo"):
            return
        self._select_report_placeholder_entry_by_text(self._report_placeholder_combo.currentText())

    def _refresh_report_placeholder_choices(self, result: Optional[Dict[str, Any]] = None) -> None:
        current_token = None
        current_entry = self._selected_report_placeholder_entry() if hasattr(self, "_report_placeholder_combo") else None
        if current_entry is not None:
            current_token = current_entry.get("token")

        if result is None:
            selected_results = self._selected_report_results() if hasattr(self, "_report_result_selectors") else []
            computed_result = self._build_report_render_context(selected_results)
            result = computed_result if computed_result else (self._result if isinstance(self._result, dict) else None)

        self._report_placeholder_entries = list_report_template_placeholders(result)
        if not hasattr(self, "_report_placeholder_combo"):
            return

        self._report_placeholder_combo.blockSignals(True)
        self._report_placeholder_combo.clear()
        for entry in self._report_placeholder_entries:
            self._report_placeholder_combo.addItem(self._report_placeholder_display_text(entry))
        if self._report_placeholder_entries:
            target_index = next(
                (index for index, entry in enumerate(self._report_placeholder_entries) if entry.get("token") == current_token),
                0,
            )
            self._report_placeholder_combo.setCurrentIndex(target_index)
        self._report_placeholder_combo.blockSignals(False)
        self._refresh_report_placeholder_completer()
        self._on_report_placeholder_changed(self._report_placeholder_combo.currentIndex())

    def _on_report_placeholder_changed(self, _index: int) -> None:
        entry = self._selected_report_placeholder_entry()
        if entry is None:
            self._report_placeholder_hint.setText("")
            return
        self._report_placeholder_hint.setText(
            f"{self._report_placeholder_group_prefix(entry)}{entry['token']}：{entry['description']}"
        )

    def _insert_selected_report_placeholder(self) -> None:
        self._select_report_placeholder_entry_from_editor_text()
        entry = self._selected_report_placeholder_entry()
        if entry is None:
            return
        self._report_editor.insertPlainText(entry["token"])
        self._report_editor.setFocus()

    def _sync_report_editor_from_template(self) -> None:
        self._load_report_template_by_id(self._current_report_template_id)

    def _apply_report_preview_theme(self) -> None:
        dark = isDarkTheme()
        bg = "#1e1e1e" if dark else "#ffffff"
        fg = "#f5f5f5" if dark else "#202020"
        border = "#3a3a3a" if dark else "#d9d9d9"
        selection_bg = accent_color()
        selection_fg = "#ffffff"
        style = (
            f"background: {bg};"
            f"color: {fg};"
            f"border: 1px solid {border};"
            "border-radius: 6px;"
            f"selection-background-color: {selection_bg};"
            f"selection-color: {selection_fg};"
        )
        self._report_editor.setStyleSheet(style)
        self._report_preview.setStyleSheet(style)

    def _render_report_preview(self) -> None:
        from core.analysis_engine import render_report

        content = self._report_editor.toPlainText()
        selected_results = self._selected_report_results()
        render_context = self._build_report_render_context(selected_results)
        self._refresh_report_placeholder_choices(render_context)
        rendered = render_report(content, render_context)
        self._report_preview.setPlainText(rendered)

    def _find_report_template_by_name(self, name: str) -> Optional[str]:
        clean_name = name.strip()
        if not clean_name:
            return None
        for template in global_assets.list_report_templates(include_builtin=False):
            if (template.name or "").strip() == clean_name:
                return template.id
        return None

    def _save_report_template_as_named(self, name: str) -> bool:
        clean_name = name.strip()
        if not clean_name or clean_name == "默认模板":
            return False
        content = self._report_editor.toPlainText()
        template_id = self._find_report_template_by_name(clean_name)
        if template_id is not None:
            if not project_manager.update_report_template(template_id, name=clean_name, content=content):
                return False
            template = project_manager.get_report_template(template_id)
            if template is None:
                return False
        else:
            template = project_manager.add_report_template(clean_name, content)
            if template is None:
                return False
        self._current_report_template_id = template.id
        self._current_report_template_name = template.name
        self._report_template_label.setText(f"当前报告模板: {self._current_report_template_name}")
        self._refresh_report_template_combo(template.id)
        self.project_modified.emit()
        return True

    def _build_report_render_context(self, selected_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = [item for item in selected_results if isinstance(item, dict) and isinstance(item.get("result"), dict)]
        primary = dict(results[0]["result"]) if results else dict(self._result or {})
        if not results and primary:
            results = [{
                "title": primary.get("title") or primary.get("source_name") or self._analysis_type_label(primary.get("analysis_type", "")),
                "result": primary,
            }]

        def _unique_join(values: List[str], separator: str = "、") -> str:
            seen: List[str] = []
            for value in values:
                clean_value = value.strip()
                if clean_value and clean_value not in seen:
                    seen.append(clean_value)
            return separator.join(seen)

        def _table_cell(value: str) -> str:
            clean_value = (value or "").replace("\n", " ").strip()
            return clean_value.replace("|", "\\|") if clean_value else "-"

        def _metric_summary(result: Dict[str, Any]) -> str:
            analysis_type = result.get("analysis_type", "")
            if analysis_type == "curve_fit":
                parts = []
                if result.get("model"):
                    parts.append(str(result["model"]))
                if result.get("r2") is not None:
                    parts.append(f"R²={result['r2']:.4f}")
                return "；".join(parts) or "-"
            if analysis_type == "statistics":
                n = result.get("n")
                y_mean = result.get("y_mean")
                if n in (None, ""):
                    return "-"
                suffix = f"，Y均值={y_mean:.6g}" if y_mean is not None else ""
                return f"N={n}{suffix}"
            if analysis_type == "correlation" and result.get("r") is not None:
                return f"r={result['r']:.6f}"
            if analysis_type == "peak_detect":
                return f"峰值={len(result.get('peaks', []) or [])}，波谷={len(result.get('valleys', []) or [])}"
            if analysis_type == "error_compare":
                return f"MAE={result.get('mae', 0):.6f}，RMSE={result.get('rmse', 0):.6f}"
            if analysis_type == "spectrum_analysis":
                return (
                    f"主频={result.get('dominant_frequency', 0):.6g} Hz，"
                    f"主峰幅值={result.get('dominant_amplitude', 0):.6g}"
                )
            return "-"

        def _params_table(result: Dict[str, Any]) -> Optional[str]:
            params = list(result.get("params", []) or [])
            names = list(result.get("param_names", []) or [])
            if not params or not names:
                return None
            rows = ["| 参数 | 值 |", "|------|-----|"]
            rows.extend(f"| {name} | {value:.6g} |" for name, value in zip(names, params))
            return "\n".join(rows)

        def _points_table(title: str, points: List[dict]) -> Optional[str]:
            if not points:
                return None
            rows = [f"#### {title}", "", "| # | X | Y |", "|---|---|---|"]
            rows.extend(
                f"| {index + 1} | {point['x']:.6g} | {point['y']:.6g} |"
                for index, point in enumerate(points[:50])
            )
            return "\n".join(rows)

        def _result_section(item: Dict[str, Any]) -> str:
            result = dict(item.get("result", {}))
            title = str(item.get("title") or self._analysis_type_label(result.get("analysis_type", "")) or "分析结果")
            lines = [f"### {title}", "", f"- 分析类型：{self._analysis_type_label(result.get('analysis_type', ''))}"]
            if result.get("source_name"):
                lines.append(f"- 数据来源：{result.get('source_name')}")
            if result.get("model"):
                lines.append(f"- 拟合模型：{result.get('model')}")
            if result.get("equation"):
                lines.append(f"- 拟合方程：{result.get('equation')}")
            summary = _metric_summary(result)
            if summary and summary != "-":
                lines.append(f"- 关键指标：{summary}")
            if result.get("n") not in (None, ""):
                lines.append(f"- 样本数：{result.get('n')}")
            params_table = _params_table(result)
            if params_table:
                lines.extend(["", params_table])
            peaks_table = _points_table("峰值列表", list(result.get("peaks", []) or []))
            if peaks_table:
                lines.extend(["", peaks_table])
            valleys_table = _points_table("波谷列表", list(result.get("valleys", []) or []))
            if valleys_table:
                lines.extend(["", valleys_table])
            return "\n".join(lines).strip()

        result_titles = [str(item.get("title") or self._analysis_type_label(item["result"].get("analysis_type", "")) or "分析结果") for item in results]
        analysis_types = [self._analysis_type_label(item["result"].get("analysis_type", "")) for item in results]
        source_names = [str(item["result"].get("source_name", "")) for item in results]
        overview_rows = ["| 结果 | 类型 | 数据来源 | 关键指标 |", "|------|------|----------|----------|"]
        for item, title in zip(results, result_titles):
            result = dict(item.get("result", {}))
            overview_rows.append(
                f"| {_table_cell(title)} | {_table_cell(self._analysis_type_label(result.get('analysis_type', '')))} | "
                f"{_table_cell(str(result.get('source_name', '')))} | {_table_cell(_metric_summary(result))} |"
            )

        context = dict(primary)
        context["_primary_result"] = primary
        context["result_count"] = str(len(results) if results else (1 if primary else 0))
        context["result_names"] = _unique_join(result_titles)
        context["analysis_type"] = _unique_join(analysis_types)
        context["source_name"] = _unique_join(source_names, separator="；")
        context["name1"] = context.get("result_names", "")
        context["name2"] = ""
        context["multi_result_sections"] = "\n\n".join(_result_section(item) for item in results if item.get("result"))
        context["_analysis_results_table"] = "\n".join(overview_rows) if len(overview_rows) > 2 else "_（无分析结果）_"
        return context

    def _save_report_template_as(self) -> None:
        name, ok = TextInputDialog.get_text(self, "另存为报告模板", "模板名称:", placeholder="输入模板名称")
        if not ok or not name.strip():
            return
        if self._save_report_template_as_named(name):
            InfoBar.success("已保存", f"模板 {name.strip()} 已保存", parent=self, position=InfoBarPosition.TOP)

    def _save_current_report_template(self) -> None:
        content = self._report_editor.toPlainText()
        if self._current_report_template_id:
            if project_manager.update_report_template(self._current_report_template_id, content=content):
                self._refresh_report_template_combo(self._current_report_template_id)
                self.project_modified.emit()
                InfoBar.success("已保存", "当前报告模板已更新", parent=self, position=InfoBarPosition.TOP)
                return
        self._save_report_template_as()

    def _export_report_to_path(self, path: str) -> bool:
        if not path:
            return False
        rendered = self._report_preview.toPlainText()
        if not rendered:
            self._render_report_preview()
            rendered = self._report_preview.toPlainText()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(rendered)
        return True

    def _export_report(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出分析报告",
            "analysis_report.md",
            "Markdown (*.md);;所有文件 (*)",
        )
        if not path:
            return
        if self._export_report_to_path(path):
            InfoBar.success("导出成功", path, parent=self, position=InfoBarPosition.TOP)

    def load_report_template(self, template_node_id: str) -> None:
        self._load_report_template_by_id(template_node_id, announce=True)

    def _current_analysis_params(self) -> Dict[str, Any]:
        analysis_type = self._current_analysis_type()
        active_inputs = self._analysis_input_payloads(analysis_type)
        params: Dict[str, Any] = {
            "analysis_type": analysis_type,
            "input_refs": [dict(item) for item in self._selected_inputs],
            "active_input_refs": [dict(item) for item in active_inputs],
        }
        if extension_registry.get_analysis(analysis_type) is not None:
            extension = extension_registry.get_analysis(analysis_type)
            lines_number = extension_lines_number(extension)
            _, effective_options = self._effective_extension_analysis_options(
                analysis_type,
                self._current_extension_analysis_options(analysis_type),
            )
            persisted_options = dict(effective_options)
            if self._extension_uses_current_input(lines_number):
                persisted_options.pop("lines_list", None)
            params["extension_options"] = persisted_options
        return params

    def _restore_analysis_params(self, params: Dict[str, Any]) -> None:
        analysis_type = str(params.get("analysis_type", "") or "")
        extension_options = params.get("extension_options")
        if analysis_type and extension_registry.get_analysis(analysis_type) is not None and isinstance(extension_options, dict):
            restored_options = dict(extension_options)
            if self._extension_uses_current_input(extension_lines_number(extension_registry.get_analysis(analysis_type))):
                restored_options.pop("lines_list", None)
            self._analysis_extension_options[analysis_type] = restored_options
            if hasattr(self, "_extension_panel"):
                self._extension_panel.set_entries(
                    self._analysis_extension_entries(),
                    saved_options=self._analysis_extension_options,
                    current_type=analysis_type,
                )
            self._sync_extension_params_editor(analysis_type)

    def _analysis_inputs_payloads(self, analysis) -> List[dict]:
        payloads: List[dict] = []
        raw_input_refs = analysis.params.get("input_refs", []) if isinstance(analysis.params, dict) else []
        for item in raw_input_refs:
            if not isinstance(item, dict):
                continue
            kind = item.get("kind")
            node_id = item.get("node_id")
            if not kind or not node_id:
                continue
            series = project_manager.get_series_from_node(kind, node_id)
            if series is None:
                continue
            payloads.append({
                "kind": kind,
                "node_id": node_id,
                "label": item.get("label") or series.name,
            })
        if not payloads:
            project = project_manager.current_project
            for series_id in analysis.input_series_ids:
                if project is not None:
                    series = project.find_series(series_id)
                else:
                    series = None
                if series is not None:
                    payloads.append({"kind": "series", "node_id": series_id, "label": series.name})
                    continue
                curve = project_manager.get_curve(series_id)
                if curve is not None:
                    payloads.append({"kind": "curve", "node_id": series_id, "label": curve.name})
        return payloads

    def _restore_analysis_inputs(self, analysis) -> None:
        payloads = self._analysis_inputs_payloads(analysis)
        self._selected_inputs = payloads
        self._rebuild_input_list()

    def _rehydrate_saved_result_payload(self, analysis) -> Dict[str, Any]:
        result = dict(analysis.summary or {})
        result.setdefault("analysis_type", analysis.analysis_type)
        if analysis.result_series_id is None:
            return result
        project = project_manager.current_project
        if project is None:
            return result
        series = project.find_series(analysis.result_series_id)
        if series is None:
            return result
        if "_plot_series" not in result and isinstance(result.get("plot_series"), list):
            result["_plot_series"] = [dict(item) for item in result.get("plot_series", []) if isinstance(item, dict)]
        if analysis.analysis_type == "curve_fit":
            result.setdefault("fit_x", list(series.x))
            result.setdefault("fit_y", list(series.y))
            result.setdefault("lines", [{"line_name": "拟合曲线", "line": line_from_xy(series.x, series.y)}])
            result.setdefault("_plot_series", [{"name": "拟合曲线", "line": "拟合曲线", "color": "#D13438"}])
        elif analysis.analysis_type == "error_compare":
            result.setdefault("error_x", list(series.x))
            result.setdefault("error_y", list(series.y))
            result.setdefault("lines", [{"line_name": "误差曲线", "line": line_from_xy(series.x, series.y)}])
            result.setdefault("_plot_series", [{"name": "误差", "line": "误差曲线", "color": "#D13438"}])
        return result

    def _rehydrate_saved_result(self, analysis) -> None:
        self._result = self._rehydrate_saved_result_payload(analysis)

    def _clear_loaded_analysis_tabs(self) -> None:
        for index in range(self._analysis_tabs.count() - 1, 0, -1):
            tab_key = self._analysis_tab_key_for_index(index)
            view = self._analysis_tab_views.get(tab_key) if tab_key else None
            self._analysis_tabs.removeTab(index)
            if view is not None and view.get("widget") is not None:
                view["widget"].deleteLater()
        current_view = self._analysis_tab_views.get("current")
        self._analysis_tab_views = {"current": current_view} if current_view is not None else {}
        self._analysis_tab_keys = ["current"] if current_view is not None else []
        self._refresh_report_result_selectors()

    def _ensure_analysis_result_tab(self, tab_key: str, title: str) -> Dict[str, Any]:
        view = self._analysis_tab_views.get(tab_key)
        if view is None:
            view = self._create_analysis_result_view(self._analysis_tabs)
            self._analysis_tab_views[tab_key] = view
            self._analysis_tab_keys.append(tab_key)
            self._analysis_tabs.addTab(view["widget"], title)
        index = self._analysis_tab_keys.index(tab_key)
        self._analysis_tabs.setTabText(index, title)
        view["analysis_name"] = title
        return view

    def _open_analysis_result_tab(self, analysis, announce: bool = False, set_active: bool = True) -> None:
        analysis_type = analysis.analysis_type or "curve_fit"
        view = self._ensure_analysis_result_tab(analysis.id, analysis.name or "分析结果")
        inputs = self._analysis_inputs_payloads(analysis)
        result = self._rehydrate_saved_result_payload(analysis)
        selected = self._get_data_for_inputs(inputs)
        view["result"] = dict(result)
        view["analysis_type"] = analysis_type
        view["selected"] = list(selected)
        view["inputs"] = [dict(item) for item in inputs]
        view["params"] = dict(analysis.params or {})
        self._render_result_view(view, analysis_type, selected, result)
        tab_index = self._analysis_tab_keys.index(analysis.id)
        if set_active:
            self._analysis_tabs.setCurrentIndex(tab_index)
            self._sync_state_from_analysis_view(view)
        if announce:
            InfoBar.success(
                "已加载分析结果",
                analysis.name or "分析结果",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2500,
            )

    def _sync_related_analysis_tabs(self) -> None:
        self._refresh_current_analysis_preview()
        self._refresh_report_result_selectors()

    def load_analysis_result(self, analysis_node_id: str) -> None:
        project = project_manager.current_project
        if project is None:
            return
        node = project_manager.get_node_by_id(analysis_node_id)
        if node is None or node.kind != "analysis_result":
            return
        analysis = project.find_analysis(node.analysis_id)
        if analysis is None:
            return
        self._result_tabs.setCurrentIndex(0)
        self._open_analysis_result_tab(analysis, announce=True, set_active=True)

    # ─────────────────────────────────────────────────────────
    # 外部接口
    # ─────────────────────────────────────────────────────────

    def _refresh_result_views(self) -> None:
        for view in self._analysis_tab_views.values():
            self._apply_result_canvas_background(view.get("canvas"))
            result = view.get("result")
            if not result:
                continue
            self._render_result_view(
                view,
                view.get("analysis_type") or result.get("analysis_type", ""),
                view.get("selected") or [],
                result,
            )

    def update_theme(self):
        self._apply_report_preview_theme()
        self._apply_result_canvas_background(self._canvas)
        if not self.isVisible():
            self._theme_refresh_pending = True
            return
        self._theme_refresh_pending = False
        QTimer.singleShot(0, self._refresh_result_views)
