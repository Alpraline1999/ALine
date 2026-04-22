"""分析页

布局：左侧配置（类型/已选数据/参数）| 右侧结果（图表 + 文本摘要 + 报告）
支持：曲线拟合、峰值检测、统计分析、相关性分析
新功能（v0.3）：通过共享项目树选择数据，Markdown 报告模板导出
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set

from PySide6.QtCore import Qt, Signal, QStringListModel
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCompleter, QFileDialog, QHBoxLayout, QHeaderView, QListWidgetItem, QSplitter,
    QStackedWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    Action,
    BodyLabel, CaptionLabel, ComboBox, EditableComboBox, FluentIcon as FIF,
    CardWidget,
    InfoBar, InfoBarPosition, LineEdit,
    ListWidget, PlainTextEdit, PrimaryPushButton, PushButton, TableWidget,
    RoundMenu,
    TabCloseButtonDisplayMode, TabWidget, TeachingTipTailPosition, ToolButton,
)

from ui.matplotlib_fonts import configure_matplotlib_cjk
from ui.dialogs.fluent_dialogs import TextInputDialog
from ui.dialogs.export_flow import (
    DataCreateTargetOption,
    choose_analysis_result_save_plan,
    choose_data_export_plan,
)
from models.schemas import DataSeries
from core.analysis_engine import list_report_template_placeholders, run_analysis
from core.shortcut_manager import ShortcutBindingSet
from ui.widgets.extension_panel import ExtensionConfigPanel
from ui.widgets.onboarding import OnboardingStep, PageOnboardingController
from ui.theme import WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_MIN_WIDTH, WORKBENCH_TOOL_PANEL_WIDTH, apply_button_metrics, make_hint_label, make_section_label, make_hsep
from core.extension_api import build_extension_entry, extension_registry, reload_configured_extensions
from core.global_assets import global_assets
from core.project_manager import project_manager

try:
    import matplotlib
    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    from qfluentwidgets import isDarkTheme
    configure_matplotlib_cjk(matplotlib)
    _HAS_MPL = True
except Exception:
    _HAS_MPL = False

_ANALYSIS_TYPES = [
    ("曲线拟合",   "curve_fit"),
    ("峰值检测",   "peak_detect"),
    ("统计分析",   "statistics"),
    ("相关性分析", "correlation"),
    ("误差比较",   "error_compare"),
]
_TYPE_LABELS = [t[0] for t in _ANALYSIS_TYPES]
_TYPE_IDS    = [t[1] for t in _ANALYSIS_TYPES]

_FIT_MODEL_LABELS = ["线性 (ax+b)", "幂函数 (a·x^b)", "指数 (a·e^(bx))",
                     "高斯", "2次多项式", "3次多项式"]
_FIT_MODEL_IDS    = ["linear", "power", "exponential", "gaussian", "poly2", "poly3"]


class _SelectableResultTable(TableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection_to_clipboard()
            event.accept()
            return
        super().keyPressEvent(event)

    def copy_selection_to_clipboard(self) -> None:
        ranges = self.selectedRanges()
        if not ranges:
            return
        selected_range = ranges[0]
        rows: List[str] = []
        for row in range(selected_range.topRow(), selected_range.bottomRow() + 1):
            cells: List[str] = []
            for column in range(selected_range.leftColumn(), selected_range.rightColumn() + 1):
                item = self.item(row, column)
                cells.append("" if item is None else item.text())
            rows.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(rows))

    def _show_context_menu(self, pos) -> None:
        menu = RoundMenu(parent=self)
        copy_action = Action(FIF.COPY, "复制选中内容", self)
        copy_action.triggered.connect(self.copy_selection_to_clipboard)
        copy_action.setEnabled(bool(self.selectedRanges()))
        menu.addAction(copy_action)
        menu.exec(self.viewport().mapToGlobal(pos))


class _SelectableResultList(ListWidget):
    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection_to_clipboard()
            event.accept()
            return
        super().keyPressEvent(event)

    def copy_selection_to_clipboard(self) -> None:
        items = self.selectedItems()
        if not items:
            return
        QApplication.clipboard().setText("\n".join(item.text() for item in items))


class AnalysisPage(QWidget):
    """数据分析页 — 通过共享项目树选择分析数据。"""

    extensions_reloaded = Signal()
    project_modified = Signal()

    # 由 main_window 框架路由的节点类型
    tree_filter_kinds: List[str] = [
        "folder", "data_file", "image_work", "global_report_template", "series", "curve",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._extension_panel_visible = False
        self._extension_panel_width = 360
        self._result: Optional[Dict[str, Any]] = None
        self._analysis_type_labels: List[str] = list(_TYPE_LABELS)
        self._analysis_type_ids: List[str] = list(_TYPE_IDS)
        self._analysis_label_map: Dict[str, str] = {type_id: label for label, type_id in _ANALYSIS_TYPES}
        self._analysis_extension_options: Dict[str, Dict[str, Any]] = {}
        # 已选分析数据列表：List[{"kind": str, "node_id": str, "label": str}]
        self._selected_inputs: List[dict] = []
        self._current_report_template_id: Optional[str] = None
        self._current_report_template_name: str = "默认模板"
        self._report_template_ids: List[Optional[str]] = [None]
        self._analysis_tab_views: Dict[str, Dict[str, Any]] = {}
        self._analysis_tab_keys: List[str] = []
        self._report_result_selectors: Dict[str, ComboBox] = {}
        self._report_result_selector_keys: Dict[str, List[Optional[str]]] = {}
        self._report_placeholder_completer: Optional[QCompleter] = None
        self._report_placeholder_search_model: Optional[QStringListModel] = None
        self._selected_tree_kind: Optional[str] = None
        self._selected_tree_node_id: Optional[str] = None
        self._report_placeholder_entries = list_report_template_placeholders()
        self._shortcut_bindings = ShortcutBindingSet()
        self._setup_ui()
        self._apply_report_preview_theme()
        self._setup_shortcuts()
        self._onboarding_controller = PageOnboardingController(self, "analysis", self._analysis_onboarding_steps)

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
        self._page_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._page_splitter.setHandleWidth(4)
        root.addWidget(self._page_splitter, 1)

        self._content_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._content_splitter.setHandleWidth(4)
        self._content_splitter.addWidget(self._build_left())
        self._content_splitter.addWidget(self._build_right())
        self._content_splitter.setSizes([320, 660])
        self._page_splitter.addWidget(self._content_splitter)

        self._extension_panel = ExtensionConfigPanel("分析扩展", "应用扩展", self)
        self._extension_panel.set_context("数据分析", "未选择输入")
        self._extension_panel.set_status_context("analysis", "分析扩展")
        self._extension_panel.apply_requested.connect(self._on_analysis_extension_apply)
        self._extension_panel.reload_requested.connect(self._reload_analysis_extensions)
        self._extension_panel.setMinimumWidth(self._extension_panel_width)
        self._extension_panel.setMaximumWidth(self._extension_panel_width)
        self._page_splitter.addWidget(self._extension_panel)
        self._page_splitter.setStretchFactor(0, 1)
        self._page_splitter.setStretchFactor(1, 0)
        self._refresh_analysis_type_choices()
        self.set_extension_panel_visible(self._extension_panel_visible)

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
            content_width = max(self.width() - self._extension_panel_width - 24, 640)
            self._page_splitter.setSizes([content_width, self._extension_panel_width])
            return
        self._extension_panel.hide()
        self._page_splitter.setSizes([1, 0])

    def _build_left(self) -> QWidget:
        panel = CardWidget(self)
        self._tool_panel = panel
        panel.setFixedWidth(WORKBENCH_TOOL_PANEL_WIDTH)
        lv = QVBoxLayout(panel)
        lv.setContentsMargins(14, 14, 14, 14)
        lv.setSpacing(8)

        lv.addWidget(make_section_label("分析类型"))
        self._type_combo = ComboBox(self)
        self._type_combo.setFixedHeight(WORKBENCH_BUTTON_HEIGHT)
        self._type_combo.addItems(self._analysis_type_labels)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        lv.addWidget(self._type_combo)

        lv.addWidget(make_hsep())
        lv.addWidget(make_section_label("分析输入（从项目树中双击添加）"))

        self._input_hint_label = make_hint_label("双击一条数据作为当前分析输入")
        self._input_hint_label.hide()
        lv.addWidget(self._input_hint_label)

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
        lv.addWidget(self._input_list)

        clear_row = QHBoxLayout()
        self._btn_clear_inputs = PushButton(FIF.DELETE, "清除", self)
        apply_button_metrics(self._btn_clear_inputs, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        self._btn_clear_inputs.clicked.connect(self._clear_inputs)
        clear_row.addWidget(self._btn_clear_inputs)
        self._btn_remove_selected_inputs = PushButton(FIF.REMOVE, "移除选中", self)
        apply_button_metrics(self._btn_remove_selected_inputs, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        self._btn_remove_selected_inputs.clicked.connect(self._remove_selected_inputs)
        clear_row.addWidget(self._btn_remove_selected_inputs)
        lv.addLayout(clear_row)

        lv.addWidget(make_hsep())
        lv.addWidget(make_section_label("参数"))

        self._fit_model_label = BodyLabel("拟合模型:")
        self._fit_model_combo = ComboBox(self)
        self._fit_model_combo.addItems(_FIT_MODEL_LABELS)
        lv.addWidget(self._fit_model_label)
        lv.addWidget(self._fit_model_combo)

        self._peak_height_label = BodyLabel("最小高度（留空自动）:")
        self._peak_height_edit = LineEdit(self)
        self._peak_height_edit.setPlaceholderText("自动")
        self._peak_dist_mode_label = BodyLabel("最小间距方式:")
        self._peak_dist_mode_combo = ComboBox(self)
        self._peak_dist_mode_combo.addItems(["采样点数", "X 值间距"])
        self._peak_dist_label = BodyLabel("最小间距:")
        self._peak_dist_edit = LineEdit(self)
        self._peak_dist_edit.setText("1")
        self._peak_prom_label = BodyLabel("最小突出度（留空不限）:")
        self._peak_prom_edit = LineEdit(self)
        self._peak_prom_edit.setPlaceholderText("不限")
        lv.addWidget(self._peak_height_label)
        lv.addWidget(self._peak_height_edit)
        lv.addWidget(self._peak_dist_mode_label)
        lv.addWidget(self._peak_dist_mode_combo)
        lv.addWidget(self._peak_dist_label)
        lv.addWidget(self._peak_dist_edit)
        lv.addWidget(self._peak_prom_label)
        lv.addWidget(self._peak_prom_edit)

        self._corr_method_label = BodyLabel("相关系数类型:")
        self._corr_method_combo = ComboBox(self)
        self._corr_method_combo.addItems(["Pearson", "Spearman"])
        lv.addWidget(self._corr_method_label)
        lv.addWidget(self._corr_method_combo)

        self._extension_params_label = BodyLabel("扩展参数 JSON:")
        self._extension_params_edit = PlainTextEdit(self)
        self._extension_params_edit.setPlaceholderText('{\n  "option": "value"\n}')
        self._extension_params_edit.setMinimumHeight(160)
        lv.addWidget(self._extension_params_label)
        lv.addWidget(self._extension_params_edit)

        lv.addStretch()
        lv.addWidget(make_hsep())

        run_btn = PrimaryPushButton(FIF.PLAY, "运行分析")
        run_btn.clicked.connect(self._run_analysis)
        apply_button_metrics(run_btn, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        lv.addWidget(run_btn)

        self._save_result_btn = PushButton(FIF.SAVE, "保存分析结果")
        self._save_result_btn.clicked.connect(self._save_result)
        apply_button_metrics(self._save_result_btn, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        lv.addWidget(self._save_result_btn)

        self._export_result_series_btn = PushButton(FIF.SHARE, "导出结果数据")
        self._export_result_series_btn.clicked.connect(self._export_result_series)
        self._export_result_series_btn.setVisible(False)
        self._export_result_series_btn.setEnabled(False)
        apply_button_metrics(self._export_result_series_btn, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        lv.addWidget(self._export_result_series_btn)

        self._export_peaks_btn = PushButton("导出波峰曲线")
        self._export_peaks_btn.clicked.connect(lambda: self._export_extrema_series("peaks", "peaks"))
        apply_button_metrics(self._export_peaks_btn, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        lv.addWidget(self._export_peaks_btn)

        self._export_valleys_btn = PushButton("导出波谷曲线")
        self._export_valleys_btn.clicked.connect(lambda: self._export_extrema_series("valleys", "valleys"))
        apply_button_metrics(self._export_valleys_btn, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        lv.addWidget(self._export_valleys_btn)

        report_btn = PushButton(FIF.DOCUMENT, "生成报告")
        report_btn.clicked.connect(self._on_generate_report)
        apply_button_metrics(report_btn, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        lv.addWidget(report_btn)

        self._report_template_label = BodyLabel("当前报告模板: 默认模板")
        self._report_template_label.setWordWrap(True)
        self._report_template_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._report_template_label.hide()
        lv.addWidget(self._report_template_label)

        self._on_type_changed(0)
        return panel

    def _build_right(self) -> QWidget:
        panel = CardWidget(self)
        rv = QVBoxLayout(panel)
        rv.setContentsMargins(14, 14, 14, 14)
        rv.setSpacing(8)
        self._result_tabs = TabWidget(panel)
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
        self._analysis_tabs.addTab(current_view["widget"], "当前结果")
        result_layout.addWidget(self._analysis_tabs, stretch=1)

        report_tab = QWidget(panel)
        report_layout = QVBoxLayout(report_tab)
        report_layout.setContentsMargins(0, 0, 0, 0)
        report_layout.setSpacing(6)
        report_layout.addWidget(make_section_label("报告模板"))

        template_row = QHBoxLayout()
        self._report_template_combo = ComboBox(panel)
        template_row.addWidget(self._report_template_combo, 1)
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
        report_layout.addLayout(template_row)

        placeholder_row = QHBoxLayout()
        self._report_placeholder_combo = EditableComboBox(panel)
        self._configure_report_placeholder_combo()
        self._report_placeholder_combo.currentIndexChanged.connect(self._on_report_placeholder_changed)
        placeholder_row.addWidget(self._report_placeholder_combo, 1)
        self._btn_insert_report_placeholder = PushButton(FIF.ADD, "插入占位符", panel)
        self._btn_insert_report_placeholder.clicked.connect(self._insert_selected_report_placeholder)
        placeholder_row.addWidget(self._btn_insert_report_placeholder)
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
        if _HAS_MPL:
            figure = Figure(figsize=(6, 4))
            canvas = FigureCanvas(figure)
            canvas.setMinimumHeight(300)
            self._apply_result_canvas_background(canvas)
            layout.addWidget(canvas, stretch=2)
        else:
            layout.addWidget(BodyLabel("需要 matplotlib"), stretch=2)

        layout.addWidget(make_hsep())
        layout.addWidget(make_section_label("摘要"))
        summary_stack = QStackedWidget(widget)
        summary_stack.setMinimumHeight(280)
        summary_table = _SelectableResultTable(widget)
        self._configure_result_table(summary_table, ["数据类型", "结果"])
        summary_stack.addWidget(summary_table)

        peak_summary_widget = QWidget(summary_stack)
        peak_summary_layout = QHBoxLayout(peak_summary_widget)
        peak_summary_layout.setContentsMargins(0, 0, 0, 0)
        peak_summary_layout.setSpacing(6)
        peak_meta_panel = QWidget(peak_summary_widget)
        peak_meta_layout = QVBoxLayout(peak_meta_panel)
        peak_meta_layout.setContentsMargins(0, 0, 0, 0)
        peak_meta_layout.setSpacing(6)
        peak_meta_layout.addWidget(make_section_label("摘要信息", peak_meta_panel))
        peak_meta_table = _SelectableResultTable(peak_meta_panel)
        self._configure_result_table(peak_meta_table, ["项目", "结果"])
        peak_meta_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        peak_meta_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        peak_meta_layout.addWidget(peak_meta_table)
        peak_summary_layout.addWidget(peak_meta_panel, stretch=2)

        peak_points_panel = QWidget(peak_summary_widget)
        peak_points_layout = QVBoxLayout(peak_points_panel)
        peak_points_layout.setContentsMargins(0, 0, 0, 0)
        peak_points_layout.setSpacing(6)
        peak_points_layout.addWidget(make_section_label("峰谷明细", peak_points_panel))
        peak_points_table = _SelectableResultTable(peak_points_panel)
        self._configure_result_table(peak_points_table, ["波峰序号", "波峰 X", "波峰 Y", "波谷序号", "波谷 X", "波谷 Y"])
        peak_points_header = peak_points_table.horizontalHeader()
        peak_points_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        peak_points_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        peak_points_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        peak_points_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        peak_points_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        peak_points_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        peak_points_layout.addWidget(peak_points_table, stretch=1)
        peak_summary_layout.addWidget(peak_points_panel, stretch=5)
        summary_stack.addWidget(peak_summary_widget)
        layout.addWidget(summary_stack, stretch=2)

        view = {
            "widget": widget,
            "figure": figure,
            "canvas": canvas,
            "summary_stack": summary_stack,
            "summary_table": summary_table,
            "peak_summary_widget": peak_summary_widget,
            "peak_meta_panel": peak_meta_panel,
            "peak_meta_table": peak_meta_table,
            "peak_points_panel": peak_points_panel,
            "peak_points_table": peak_points_table,
            "result": None,
            "analysis_type": None,
            "selected": [],
            "inputs": [],
            "params": {},
            "analysis_name": "当前结果",
        }
        self._set_summary_rows(summary_table, [("状态", "（运行分析后显示结果）")])
        self._set_summary_rows(peak_meta_table, [("状态", "（运行峰谷检测后显示结果）")])
        self._set_peak_points_rows(peak_points_table, [], [])
        return view

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

    def _peak_summary_rows(self, r: dict) -> List[tuple[str, str]]:
        distance_mode = "X 值间距" if r.get("distance_mode") == "x_distance" else "采样点数"
        distance_value = r.get("distance_value")
        rows = [
            ("波峰数量", str(r.get("count", 0))),
            ("波谷数量", str(r.get("valley_count", 0))),
            ("数据源", str(r.get("source_name", "-"))),
        ]
        if distance_value not in (None, ""):
            rows.append(("最小间距", f"{distance_value}（{distance_mode}）"))
        return rows

    def _set_peak_points_rows(self, table: TableWidget, peaks: List[dict], valleys: List[dict]) -> None:
        row_count = max(len(peaks), len(valleys))
        table.setRowCount(row_count)
        for row_idx in range(row_count):
            peak = peaks[row_idx] if row_idx < len(peaks) else None
            valley = valleys[row_idx] if row_idx < len(valleys) else None
            values = [
                self._format_summary_value(None if peak is None else row_idx + 1),
                self._format_summary_value(None if peak is None else peak.get("x")),
                self._format_summary_value(None if peak is None else peak.get("y")),
                self._format_summary_value(None if valley is None else row_idx + 1),
                self._format_summary_value(None if valley is None else valley.get("x")),
                self._format_summary_value(None if valley is None else valley.get("y")),
            ]
            for col_idx, value in enumerate(values):
                table.setItem(row_idx, col_idx, QTableWidgetItem(value))
        table.resizeRowsToContents()

    def _analysis_type_label(self, analysis_type: str) -> str:
        return self._analysis_label_map.get(analysis_type, analysis_type or "分析结果")

    def _analysis_extension_entries(self) -> List[dict]:
        return [build_extension_entry(extension) for extension in extension_registry.list_analysis()]

    def _parse_extension_analysis_options_text(self, text: Optional[str] = None) -> Dict[str, Any]:
        raw_text = text if text is not None else self._extension_params_edit.toPlainText()
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

    def _current_extension_analysis_options(self, analysis_type: Optional[str] = None, *, raise_on_error: bool = False) -> Dict[str, Any]:
        type_id = analysis_type or self._current_analysis_type()
        if type_id in _TYPE_IDS:
            return {}
        if type_id == self._current_analysis_type():
            try:
                options = self._parse_extension_analysis_options_text()
            except ValueError:
                if raise_on_error:
                    raise
                return dict(self._analysis_extension_options.get(type_id, {}))
            self._analysis_extension_options[type_id] = dict(options)
            return dict(options)
        return dict(self._analysis_extension_options.get(type_id, {}))

    def _sync_extension_params_editor(self, analysis_type: Optional[str] = None) -> None:
        type_id = analysis_type or self._current_analysis_type()
        options: Dict[str, Any] = {}
        if type_id not in _TYPE_IDS:
            if type_id in self._analysis_extension_options:
                options = dict(self._analysis_extension_options.get(type_id, {}))
            else:
                extension = extension_registry.get_analysis(type_id)
                options = dict(getattr(extension, "default_options", {}) or {}) if extension is not None else {}
                self._analysis_extension_options[type_id] = dict(options)
        self._extension_params_edit.blockSignals(True)
        self._extension_params_edit.setPlainText(json.dumps(dict(options), ensure_ascii=False, indent=2) if options else "{}")
        self._extension_params_edit.blockSignals(False)

    def _refresh_analysis_type_choices(self) -> None:
        current_type = self._current_analysis_type() if hasattr(self, "_type_combo") else None
        self._analysis_type_labels = list(_TYPE_LABELS)
        self._analysis_type_ids = list(_TYPE_IDS)
        self._analysis_label_map = {type_id: label for label, type_id in _ANALYSIS_TYPES}
        for extension in extension_registry.list_analysis():
            self._analysis_type_labels.append(f"[扩展]{extension.name}")
            self._analysis_type_ids.append(extension.type)
            self._analysis_label_map[extension.type] = extension.name
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
        for key in self._analysis_tab_keys:
            view = self._analysis_tab_views.get(key)
            if view is None:
                continue
            result = view.get("result")
            if not isinstance(result, dict) or not result:
                continue
            analysis_type = str(view.get("analysis_type") or result.get("analysis_type") or "")
            if not analysis_type:
                continue
            candidates.setdefault(analysis_type, []).append({
                "key": key,
                "title": view.get("analysis_name") or ("当前结果" if key == "current" else "分析结果"),
                "result": dict(result),
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
        summary_stack = view.get("summary_stack")
        if summary_stack is None:
            self._set_summary_rows(view["summary_table"], self._summary_rows(t, r))
            return
        if t == "peak_detect":
            summary_stack.setCurrentWidget(view["peak_summary_widget"])
            self._set_summary_rows(view["peak_meta_table"], self._peak_summary_rows(r))
            self._set_peak_points_rows(view["peak_points_table"], list(r.get("peaks", []) or []), list(r.get("valleys", []) or []))
            return
        summary_stack.setCurrentWidget(view["summary_table"])
        self._set_summary_rows(view["summary_table"], self._summary_rows(t, r))

    def _analysis_tab_key_for_index(self, index: int) -> Optional[str]:
        if 0 <= index < len(self._analysis_tab_keys):
            return self._analysis_tab_keys[index]
        return None

    def _analysis_view_for_key(self, key: str) -> Optional[Dict[str, Any]]:
        return self._analysis_tab_views.get(key)

    def _sync_state_from_analysis_view(self, view: Dict[str, Any]) -> None:
        result = view.get("result")
        if result is None:
            return
        self._figure = view.get("figure")
        self._canvas = view.get("canvas")
        self._summary_table = view.get("summary_table")
        analysis_type = view.get("analysis_type") or result.get("analysis_type", "curve_fit")
        if analysis_type in self._analysis_type_ids:
            self._type_combo.setCurrentIndex(self._analysis_type_ids.index(analysis_type))
        self._restore_analysis_params(view.get("params") or {})
        self._selected_inputs = [dict(item) for item in view.get("inputs") or []]
        self._rebuild_input_list()
        self._result = dict(result)
        self._update_peak_export_buttons()
        self._render_report_preview()

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

    # ─────────────────────────────────────────────────────────
    # 共享树接口
    # ─────────────────────────────────────────────────────────

    def on_tree_node_selected(self, kind: str, node_id: str) -> None:
        """单击选中节点（只更新高亮，不加入分析列表）。"""
        self._selected_tree_kind = kind
        self._selected_tree_node_id = node_id

    def on_tree_node_activated(self, kind: str, node_id: str) -> None:
        """双击树节点 → 加入分析输入列表。"""
        if kind.endswith("_to_analysis"):
            kind = kind[:-12]
        if kind == "global_report_template":
            self.load_report_template(node_id)
            return
        if kind not in ("series", "curve", "data_file", "image_work"):
            return
        label = self._get_node_label(kind, node_id)
        if any(inp["node_id"] == node_id for inp in self._selected_inputs):
            self._sync_related_analysis_tabs()
            return
        self._assign_input_for_current_mode({"kind": kind, "node_id": node_id, "label": label})

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

    def _clear_inputs(self):
        self._selected_inputs.clear()
        self._rebuild_input_list()
        self._sync_related_analysis_tabs()

    def _remove_selected_inputs(self):
        to_remove: Set[str] = set()
        for item in self._input_list.selectedItems():
            d = item.data(Qt.ItemDataRole.UserRole)
            if d:
                to_remove.add(d["node_id"])
        self._selected_inputs = [x for x in self._selected_inputs
                                  if x["node_id"] not in to_remove]
        self._rebuild_input_list()
        self._sync_related_analysis_tabs()

    def _assign_input_for_current_mode(self, payload: dict) -> None:
        if self._requires_pair_input():
            if len(self._selected_inputs) < 2:
                self._selected_inputs.append(payload)
            else:
                self._selected_inputs[1] = payload
        else:
            self._selected_inputs = [payload]
        self._rebuild_input_list()
        self._sync_related_analysis_tabs()

    def _rebuild_input_list(self) -> None:
        self._input_list.clear()
        for payload in self._selected_inputs:
            item = QListWidgetItem(payload["label"])
            item.setData(Qt.ItemDataRole.UserRole, {"kind": payload["kind"], "node_id": payload["node_id"]})
            item.setToolTip(payload["label"])
            self._input_list.addItem(item)
        self._sync_input_role_labels()

    def _sync_input_role_labels(self) -> None:
        primary = self._selected_inputs[0]["label"] if self._selected_inputs else "未选择"
        secondary = self._selected_inputs[1]["label"] if len(self._selected_inputs) > 1 else "未使用"
        self._primary_input_label.setText(f"主输入: {primary}")
        self._secondary_input_label.setText(f"对比输入: {secondary}")
        if hasattr(self, "_extension_panel"):
            target = primary if self._selected_inputs else "未选择输入"
            self._extension_panel.set_context("数据分析", target)

    def _current_analysis_type(self) -> str:
        idx = self._type_combo.currentIndex()
        return self._analysis_type_ids[idx] if 0 <= idx < len(self._analysis_type_ids) else "curve_fit"

    def _requires_pair_input(self) -> bool:
        return self._current_analysis_type() in {"correlation", "error_compare"}

    # ─────────────────────────────────────────────────────────
    # 类型切换
    # ─────────────────────────────────────────────────────────

    def _on_type_changed(self, idx: int):
        t = self._analysis_type_ids[idx] if idx < len(self._analysis_type_ids) else "curve_fit"
        is_fit  = t == "curve_fit"
        is_peak = t == "peak_detect"
        is_corr = t == "correlation"
        is_extension = t not in _TYPE_IDS
        for w in [self._fit_model_label, self._fit_model_combo]:
            w.setVisible(is_fit)
        for w in [self._peak_height_label, self._peak_height_edit,
                  self._peak_dist_mode_label, self._peak_dist_mode_combo,
                  self._peak_dist_label, self._peak_dist_edit,
                  self._peak_prom_label, self._peak_prom_edit]:
            w.setVisible(is_peak)
        for w in [self._corr_method_label, self._corr_method_combo]:
            w.setVisible(is_corr)
        for w in [self._extension_params_label, self._extension_params_edit]:
            w.setVisible(is_extension)
        if is_extension:
            self._sync_extension_params_editor(t)
        if self._requires_pair_input():
            self._input_hint_label.setText("按顺序双击两条数据加入分析输入列表")
        else:
            if len(self._selected_inputs) > 1:
                self._selected_inputs = self._selected_inputs[:1]
                self._rebuild_input_list()
            self._input_hint_label.setText("双击一条数据作为当前分析输入")
        self._sync_input_role_labels()
        self._update_peak_export_buttons()
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
        return self._get_data_for_inputs(self._selected_inputs)

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
        selected = self._get_selected_data()
        if not selected:
            InfoBar.warning("提示", "请先从项目树双击选择数据", parent=self,
                            position=InfoBarPosition.TOP)
            return
        t = self._current_analysis_type()
        try:
            if t == "curve_fit":
                self._result = self._do_fit(selected[0])
            elif t == "peak_detect":
                self._result = self._do_peaks(selected[0])
            elif t == "statistics":
                self._result = self._do_stats(selected[0])
            elif t == "correlation":
                if len(selected) < 2:
                    InfoBar.warning("提示", "相关性分析需要选择两条数据系列", parent=self,
                                    position=InfoBarPosition.TOP)
                    return
                self._result = self._do_correlation(selected[0], selected[1])
            elif t == "error_compare":
                if len(selected) < 2:
                    InfoBar.warning("提示", "误差比较需要选择主序列和对比序列", parent=self,
                                    position=InfoBarPosition.TOP)
                    return
                self._result = self._do_error_compare(selected[0], selected[1])
            else:
                inputs = [{"x": xs, "y": ys, "name": name} for xs, ys, name in selected]
                self._result = run_analysis(t, inputs, self._current_extension_analysis_options(t, raise_on_error=True))
            self._show_result(t, selected)
        except Exception as e:
            InfoBar.error("分析失败", str(e), parent=self, position=InfoBarPosition.TOP)
            if self._summary_table is not None:
                self._set_summary_rows(self._summary_table, [("错误", str(e))])

    def _do_fit(self, src: tuple) -> dict:
        from core.analysis_engine import fit_curve
        xs, ys, name = src
        model = _FIT_MODEL_IDS[self._fit_model_combo.currentIndex()]
        r = fit_curve(xs, ys, model)
        r["source_name"] = name
        r["analysis_type"] = "curve_fit"
        return r

    def _do_peaks(self, src: tuple) -> dict:
        from core.analysis_engine import detect_peaks, detect_valleys
        xs, ys, name = src
        def _f(e, default):
            try: return float(e.text())
            except: return default
        def _i(e, default):
            try: return max(1, int(e.text()))
            except: return default
        min_h = _f(self._peak_height_edit, None)
        dist_mode = "x_distance" if self._peak_dist_mode_combo.currentIndex() == 1 else "points"
        min_d = _i(self._peak_dist_edit, 1) if dist_mode == "points" else None
        min_d_x = _f(self._peak_dist_edit, 1.0) if dist_mode == "x_distance" else None
        prom = _f(self._peak_prom_edit, None)
        r_peaks = detect_peaks(xs, ys, min_height=min_h, min_distance=min_d, min_distance_x=min_d_x, prominence=prom)
        r_valleys = detect_valleys(xs, ys, min_distance=min_d, min_distance_x=min_d_x, prominence=prom)
        return {
            "peaks": r_peaks.get("peaks", []),
            "count": r_peaks.get("count", 0),
            "valleys": r_valleys.get("valleys", []),
            "valley_count": r_valleys.get("count", 0),
            "source_name": name,
            "distance_mode": dist_mode,
            "distance_value": min_d_x if dist_mode == "x_distance" else min_d,
            "analysis_type": "peak_detect",
        }

    def _do_stats(self, src: tuple) -> dict:
        from core.analysis_engine import compute_statistics
        xs, ys, name = src
        r = compute_statistics(xs, ys)
        r["source_name"] = name
        r["analysis_type"] = "statistics"
        return r

    def _do_correlation(self, src1: tuple, src2: tuple) -> dict:
        from core.analysis_engine import compute_correlation
        _, ys1, name1 = src1
        _, ys2, name2 = src2
        method = self._corr_method_combo.currentText().lower()
        r = compute_correlation(ys1, ys2, method)
        r["name1"] = name1
        r["name2"] = name2
        r["analysis_type"] = "correlation"
        return r

    def _do_error_compare(self, src1: tuple, src2: tuple) -> dict:
        from core.analysis_engine import compute_error_metrics

        xs1, ys1, name1 = src1
        xs2, ys2, name2 = src2
        result = compute_error_metrics(xs1, ys1, xs2, ys2)
        result["name1"] = name1
        result["name2"] = name2
        return result

    # ─────────────────────────────────────────────────────────
    # 结果显示
    # ─────────────────────────────────────────────────────────

    def _show_result(self, t: str, selected: list):
        r = self._result
        if r is None:
            self._update_peak_export_buttons()
            return
        view = self._analysis_tab_views.get("current")
        if view is not None:
            view["result"] = dict(r)
            view["analysis_type"] = t
            view["selected"] = list(selected)
            view["inputs"] = [dict(item) for item in self._selected_inputs]
            view["params"] = self._current_analysis_params()
            view["analysis_name"] = "当前结果"
            self._render_result_view(view, t, selected, r)
            self._analysis_tabs.setCurrentIndex(0)
        else:
            self._draw_result(t, selected, r)
            self._write_summary(t, r)
        self._refresh_report_placeholder_choices()
        self._update_peak_export_buttons()

    def _render_result_view(self, view: Dict[str, Any], t: str, selected: list, r: dict) -> None:
        self._draw_result(t, selected, r, figure=view.get("figure"), canvas=view.get("canvas"))
        self._render_summary_view(view, t, r)
        self._refresh_report_result_selectors()

    def _draw_result(self, t: str, selected: list, r: dict, figure=None, canvas=None):
        figure = self._figure if figure is None else figure
        canvas = self._canvas if canvas is None else canvas
        if not _HAS_MPL or figure is None or canvas is None:
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

        if t == "curve_fit" and selected:
            xs, ys, name = selected[0]
            ax.scatter(xs, ys, s=15, color="#888888", alpha=0.7, label=name)
            if "fit_x" in r and "fit_y" in r:
                ax.plot(r["fit_x"], r["fit_y"], color="#D13438", linewidth=2,
                        label=f"拟合 R²={r.get('r2', 0):.4f}")
            ax.legend(facecolor=bg, edgecolor=fg, labelcolor=fg, fontsize=8)

        elif t == "peak_detect" and selected:
            xs, ys, name = selected[0]
            ax.plot(xs, ys, color="#0078D4", linewidth=1.4, label=name)
            peaks = r.get("peaks", [])
            if peaks:
                px = [p["x"] for p in peaks]
                py = [p["y"] for p in peaks]
                ax.scatter(px, py, color="#D13438", s=50, zorder=5,
                           marker="^", label=f"波峰 ({len(peaks)}个)")
            valleys = r.get("valleys", [])
            if valleys:
                vx = [v["x"] for v in valleys]
                vy = [v["y"] for v in valleys]
                ax.scatter(vx, vy, color="#107C10", s=50, zorder=5,
                           marker="v", label=f"波谷 ({len(valleys)}个)")
            ax.legend(facecolor=bg, edgecolor=fg, labelcolor=fg, fontsize=8)

        elif t == "correlation" and len(selected) >= 2:
            _, ys1, n1 = selected[0]
            _, ys2, n2 = selected[1]
            nn = min(len(ys1), len(ys2))
            ax.scatter(ys1[:nn], ys2[:nn], s=15, color="#0078D4", alpha=0.7)
            ax.set_xlabel(n1, color=fg)
            ax.set_ylabel(n2, color=fg)
            ax.set_title(f"r = {r.get('r', 0):.4f}", color=fg)

        elif t == "error_compare" and len(selected) >= 2:
            ex = r.get("error_x", [])
            ey = r.get("error_y", [])
            ax.axhline(0.0, color="#888888", linestyle="--", linewidth=1.0)
            ax.plot(ex, ey, color="#D13438", linewidth=1.5, label="误差")
            ax.set_xlabel(selected[0][2], color=fg)
            ax.set_ylabel("误差", color=fg)
            ax.legend(facecolor=bg, edgecolor=fg, labelcolor=fg, fontsize=8)

        elif t == "statistics" and selected:
            xs, ys, name = selected[0]
            ax.plot(xs, ys, color="#0078D4", linewidth=1.4, label=name)
            mean = r.get("y_mean", 0)
            ax.axhline(mean, color="#D13438", linestyle="--", linewidth=1,
                       label=f"均值={mean:.4g}")
            ax.legend(facecolor=bg, edgecolor=fg, labelcolor=fg, fontsize=8)

        else:
            custom_series = list(r.get("_plot_series", []) or [])
            palette = ["#0078D4", "#D13438", "#107C10", "#8764B8"]
            plotted = False
            for index, series in enumerate(custom_series):
                xs = list(series.get("x", []) or [])
                ys = list(series.get("y", []) or [])
                if not xs or not ys or len(xs) != len(ys):
                    continue
                ax.plot(
                    xs,
                    ys,
                    color=str(series.get("color") or palette[index % len(palette)]),
                    linewidth=float(series.get("line_width", 1.6)),
                    label=str(series.get("name") or f"结果曲线 {index + 1}"),
                )
                plotted = True
            if plotted:
                if r.get("x_label"):
                    ax.set_xlabel(str(r.get("x_label")), color=fg)
                if r.get("y_label"):
                    ax.set_ylabel(str(r.get("y_label")), color=fg)
                if r.get("plot_title"):
                    ax.set_title(str(r.get("plot_title")), color=fg)
                ax.legend(facecolor=bg, edgecolor=fg, labelcolor=fg, fontsize=8)

        canvas.draw()

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

    def _summary_rows(self, t: str, r: dict) -> List[tuple[str, str]]:
        if t == "curve_fit":
            params = r.get("params", [])
            names = r.get("param_names", [])
            param_str = "  ".join(f"{n}={v:.4g}" for n, v in zip(names, params))
            return [
                ("模型", str(r.get("model", ""))),
                ("方程", str(r.get("equation", ""))),
                ("参数", param_str or "-"),
                ("R²", f"{r.get('r2', float('nan')):.6f}"),
            ]
        elif t == "peak_detect":
            return self._peak_summary_rows(r)
        elif t == "statistics":
            return [
                ("样本数 N", str(r.get("n", 0))),
                ("X 均值", f"{r.get('x_mean', 0):.4g}"),
                ("X 标准差", f"{r.get('x_std', 0):.4g}"),
                ("X 范围", f"[{r.get('x_min', 0):.4g}, {r.get('x_max', 0):.4g}]"),
                ("Y 均值", f"{r.get('y_mean', 0):.4g}"),
                ("Y 标准差", f"{r.get('y_std', 0):.4g}"),
                ("Y 范围", f"[{r.get('y_min', 0):.4g}, {r.get('y_max', 0):.4g}]"),
                ("Y 中位数", f"{r.get('y_median', 0):.4g}"),
                ("Y 四分位", f"Q1={r.get('y_p25', 0):.4g}, Q3={r.get('y_p75', 0):.4g}"),
            ]
        elif t == "correlation":
            p = r.get("p_value")
            rows = [
                ("方法", str(r.get("method", ""))),
                ("相关系数 r", f"{r.get('r', 0):.6f}"),
                ("数据", f"{r.get('name1', '')} vs {r.get('name2', '')}"),
            ]
            if p is not None:
                rows.append(("p 值", f"{p:.4g}"))
            return rows
        elif t == "error_compare":
            rel = r.get("relative_mae")
            rows = [
                ("数据", f"{r.get('name1', '')} vs {r.get('name2', '')}"),
                ("MAE", f"{r.get('mae', 0):.6f}"),
                ("RMSE", f"{r.get('rmse', 0):.6f}"),
                ("平均误差", f"{r.get('mean_error', 0):.6f}"),
                ("最大绝对误差", f"{r.get('max_abs_error', 0):.6f}"),
            ]
            if rel is not None:
                rows.append(("相对平均误差", f"{rel:.6f}"))
            return rows
        else:
            return self._json_summary_rows(r)

    def _write_summary(self, t: str, r: dict):
        current_view = self._analysis_tab_views.get("current")
        if current_view is not None:
            self._render_summary_view(current_view, t, r)
            return
        if self._summary_table is not None:
            self._set_summary_rows(self._summary_table, self._summary_rows(t, r))

    # ─────────────────────────────────────────────────────────
    # 保存分析结果
    # ─────────────────────────────────────────────────────────

    def _default_analysis_result_name(self) -> str:
        type_label = self._analysis_type_label(self._current_analysis_type())
        source_name = str((self._result or {}).get("source_name") or "").strip()
        if source_name:
            return f"{source_name}_{type_label}"
        return f"{type_label}结果"

    def _save_result(self):
        if self._result is None:
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
        for item in self._selected_inputs:
            series = project_manager.get_series_from_node(item["kind"], item["node_id"])
            if series is not None:
                input_series_ids.append(series.id)
        ar = AnalysisResult(
            name=clean_name,
            analysis_type=self._result.get("analysis_type", "analysis"),
            input_series_ids=input_series_ids,
            params=self._current_analysis_params(),
            summary=dict(self._result),
        )
        if not project_manager.add_analysis(ar, parent_id=save_plan.target_parent_id):
            InfoBar.error("保存失败", "未能保存分析结果到目标位置", parent=self, position=InfoBarPosition.TOP)
            return
        self._sync_related_analysis_tabs()
        self.project_modified.emit()
        InfoBar.success("已保存", "分析结果已保存至项目", parent=self,
                        position=InfoBarPosition.TOP)

    def _preferred_analysis_result_target_node_id(self) -> Optional[str]:
        if self._selected_tree_node_id:
            return project_manager.get_analysis_result_target_folder_id(self._selected_tree_node_id)
        return project_manager.get_analysis_result_target_folder_id(None)

    def _ensure_analysis_result_folder(self) -> Optional[str]:
        dataset_root = project_manager._find_folder_by_group_type("datasets")
        if dataset_root is None:
            return None
        for node in project_manager.get_children(dataset_root.id):
            if node.kind == "folder" and node.name == "分析结果":
                return node.id
        folder = project_manager.add_folder("分析结果", parent_id=dataset_root.id)
        return folder.id if folder is not None else None

    def _build_analysis_output_series(self, export_name: str) -> Optional[DataSeries]:
        if self._result is None:
            return None
        analysis_type = self._result.get("analysis_type", "analysis")
        custom_series = list(self._result.get("_plot_series", []) or [])
        if custom_series:
            first_series = dict(custom_series[0])
            xs = list(first_series.get("x", []) or [])
            ys = list(first_series.get("y", []) or [])
            if xs and ys and len(xs) == len(ys):
                return DataSeries(
                    name=export_name,
                    x=xs,
                    y=ys,
                    source="computed",
                )
        if analysis_type == "curve_fit" and "fit_x" in self._result:
            return DataSeries(
                name=export_name,
                x=list(self._result["fit_x"]),
                y=list(self._result["fit_y"]),
                source="computed",
            )
        if analysis_type == "error_compare" and "error_x" in self._result:
            return DataSeries(
                name=export_name,
                x=list(self._result["error_x"]),
                y=list(self._result["error_y"]),
                source="computed",
            )
        return None

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
            getattr(project_manager._find_folder_by_group_type("datasets"), "id", None),
        )

    def _analysis_output_export_button_text(self) -> str:
        analysis_type = self._result.get("analysis_type", "") if self._result else ""
        if self._result and self._result.get("_plot_series"):
            return "导出分析曲线"
        return {
            "curve_fit": "导出拟合曲线",
            "error_compare": "导出误差曲线",
        }.get(analysis_type, "导出结果数据")

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
        if self._result is None:
            InfoBar.warning("提示", "请先运行分析", parent=self, position=InfoBarPosition.TOP)
            return
        default_name = self._default_analysis_result_name()
        series = self._build_analysis_output_series(default_name)
        if series is None:
            InfoBar.warning("提示", "当前分析结果没有可导出的数据曲线", parent=self, position=InfoBarPosition.TOP)
            return
        self._export_current_series(series, title=self._analysis_output_export_button_text())

    # ─────────────────────────────────────────────────────────
    # 报告模板
    # ─────────────────────────────────────────────────────────

    def _on_generate_report(self):
        self._result_tabs.setCurrentIndex(1)
        self._render_report_preview()

    def _current_report_template_content(self) -> str:
        from core.analysis_engine import _DEFAULT_REPORT_TEMPLATE

        if self._current_report_template_id:
            template = project_manager.get_report_template(self._current_report_template_id)
            if template is not None:
                return template.content
        return _DEFAULT_REPORT_TEMPLATE

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
        from core.analysis_engine import _DEFAULT_REPORT_TEMPLATE

        content = _DEFAULT_REPORT_TEMPLATE
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
        style = (
            "PlainTextEdit {"
            f"background: {bg};"
            f"color: {fg};"
            f"border: 1px solid {border};"
            "border-radius: 6px;"
            "}"
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
        params: Dict[str, Any] = {
            "analysis_type": analysis_type,
            "input_refs": [dict(item) for item in self._selected_inputs],
        }
        if analysis_type == "curve_fit":
            params["fit_model"] = _FIT_MODEL_IDS[self._fit_model_combo.currentIndex()]
        elif analysis_type == "peak_detect":
            params.update({
                "min_height": self._peak_height_edit.text().strip(),
                "min_distance_mode": "x_distance" if self._peak_dist_mode_combo.currentIndex() == 1 else "points",
                "min_distance": self._peak_dist_edit.text().strip(),
                "prominence": self._peak_prom_edit.text().strip(),
            })
        elif analysis_type == "correlation":
            params["corr_method"] = self._corr_method_combo.currentText().strip().lower()
        elif analysis_type not in _TYPE_IDS:
            params["extension_options"] = self._current_extension_analysis_options(analysis_type)
        return params

    def _restore_analysis_params(self, params: Dict[str, Any]) -> None:
        fit_model = params.get("fit_model")
        if fit_model in _FIT_MODEL_IDS:
            self._fit_model_combo.setCurrentIndex(_FIT_MODEL_IDS.index(fit_model))
        self._peak_height_edit.setText(str(params.get("min_height", "")))
        self._peak_dist_mode_combo.setCurrentIndex(1 if params.get("min_distance_mode") == "x_distance" else 0)
        self._peak_dist_edit.setText(str(params.get("min_distance", "1")))
        self._peak_prom_edit.setText(str(params.get("prominence", "")))
        corr_method = str(params.get("corr_method", "pearson")).capitalize()
        corr_idx = self._corr_method_combo.findText(corr_method)
        if corr_idx >= 0:
            self._corr_method_combo.setCurrentIndex(corr_idx)
        analysis_type = str(params.get("analysis_type", "") or "")
        extension_options = params.get("extension_options")
        if analysis_type and analysis_type not in _TYPE_IDS and isinstance(extension_options, dict):
            self._analysis_extension_options[analysis_type] = dict(extension_options)
            if hasattr(self, "_extension_panel"):
                self._extension_panel.set_entries(
                    self._analysis_extension_entries(),
                    saved_options=self._analysis_extension_options,
                    current_type=analysis_type,
                )
            self._sync_extension_params_editor(analysis_type)

    def _update_peak_export_buttons(self) -> None:
        is_peak_mode = self._current_analysis_type() == "peak_detect"
        result = self._result or {}
        has_peak_result = bool(result and result.get("analysis_type") == "peak_detect")
        peak_count = len(result.get("peaks", [])) if has_peak_result else 0
        valley_count = len(result.get("valleys", [])) if has_peak_result else 0
        self._export_peaks_btn.setVisible(is_peak_mode)
        self._export_valleys_btn.setVisible(is_peak_mode)
        self._export_peaks_btn.setEnabled(has_peak_result and peak_count > 0)
        self._export_valleys_btn.setEnabled(has_peak_result and valley_count > 0)
        has_exportable_series = self._result is not None and self._build_analysis_output_series(self._default_analysis_result_name()) is not None
        self._export_result_series_btn.setVisible(has_exportable_series)
        self._export_result_series_btn.setEnabled(has_exportable_series)
        if has_exportable_series:
            self._export_result_series_btn.setText(self._analysis_output_export_button_text())

    def _export_extrema_series(self, result_key: str, suffix: str) -> None:
        if not self._result or self._result.get("analysis_type") != "peak_detect":
            InfoBar.warning("提示", "请先运行峰值检测", parent=self, position=InfoBarPosition.TOP)
            return
        points = list(self._result.get(result_key, []) or [])
        if not points:
            InfoBar.warning("提示", "当前结果中没有可导出的点", parent=self, position=InfoBarPosition.TOP)
            return
        project = project_manager.current_project
        if project is None:
            InfoBar.warning("提示", "没有打开的项目", parent=self, position=InfoBarPosition.TOP)
            return

        from models.schemas import DataSeries

        source_name = self._result.get("source_name", "series")
        series = DataSeries(
            name=f"{suffix}_{source_name}",
            x=[float(point["x"]) for point in points],
            y=[float(point["y"]) for point in points],
            source="computed",
        )
        self._export_current_series(series, title=f"导出{suffix}曲线")

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
        if analysis.analysis_type == "curve_fit":
            result.setdefault("fit_x", list(series.x))
            result.setdefault("fit_y", list(series.y))
        elif analysis.analysis_type == "error_compare":
            result.setdefault("error_x", list(series.x))
            result.setdefault("error_y", list(series.y))
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
        self._clear_loaded_analysis_tabs()
        if self._requires_pair_input() or not self._selected_inputs:
            return
        project = project_manager.current_project
        if project is None:
            return
        primary = self._selected_inputs[0]
        series = project_manager.get_series_from_node(primary["kind"], primary["node_id"])
        if series is None:
            return
        for analysis in project.analyses:
            if series.id in list(analysis.input_series_ids or []):
                self._open_analysis_result_tab(analysis, announce=False, set_active=False)

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

    def update_theme(self):
        self._apply_report_preview_theme()
        self._apply_result_canvas_background(self._canvas)
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
