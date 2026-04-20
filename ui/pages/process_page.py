"""数据处理页

三列布局：左侧数据选择 | 中间操作链 | 右侧效果预览
支持非破坏性操作管道，结果可另存为新数据系列或数据文件。
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QSplitter, QStackedWidget, QVBoxLayout, QWidget, QTreeWidgetItem
from qfluentwidgets import (
    BodyLabel, ComboBox, FluentIcon as FIF,
    CardWidget,
    InfoBar, InfoBarPosition, LineEdit,
    PlainTextEdit, PrimaryPushButton, ToolButton,
    TeachingTipTailPosition,
    TreeWidget, ListWidget, CheckBox, ToolTipFilter, ToolTipPosition,
)

from core.extension_api import build_extension_entry, extension_registry, reload_builtin_extensions
from core.shortcut_manager import ShortcutBindingSet
from ui.theme import WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_MIN_WIDTH, WORKBENCH_TOOL_PANEL_WIDTH, apply_button_metrics, make_section_label, make_hsep
from ui.dialogs.fluent_dialogs import TextInputDialog
from ui.dialogs.export_flow import choose_data_export_plan
from ui.widgets.extension_panel import ExtensionConfigPanel
from ui.widgets.onboarding import OnboardingStep, PageOnboardingController
from core.global_assets import global_assets
from core.project_manager import project_manager
from models.schemas import DataFile, DataSeries, SavedPipeline
from processing.data_engine import apply_pipeline

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

_OPS = [
    ("裁剪 (Crop)",            "crop"),
    ("平滑 (Smooth)",          "smooth"),
    ("归一化 (Normalize)",     "normalize"),
    ("重采样 (Resample)",      "resample"),
    ("FFT 频谱 (FFT)",        "fft"),
    ("求导 (Derivative)",      "derivative"),
    ("积分 (Integral)",        "integral"),
    ("变换表达式 (Transform)", "transform"),
    ("低/高通滤波 (Filter)", "filter"),
]
_OP_LABELS = [o[0] for o in _OPS]
_OP_TYPES  = [o[1] for o in _OPS]
_OP_TYPE_TO_LABEL = {op_type: label for label, op_type in _OPS}

_OP_HINTS = {
    "crop": "按 X 轴范围裁剪数据，只保留指定区间。",
    "smooth": "对 Y 序列做平滑处理，适合去噪。",
    "normalize": "按 min-max 或 z-score 归一化 Y 序列。",
    "resample": "把数据重采样到新的等间距点数或固定间距。",
    "fft": "将时域/空间域信号转换为频域频谱，可选指定采样频率。",
    "derivative": "计算一阶导数，观察变化速率。",
    "integral": "计算积分或累积积分。",
    "transform": "用表达式批量变换 X/Y 数据。",
    "filter": "进行低通或高通滤波，去除不需要的频率成分。",
}


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


class ProcessPage(QWidget):
    """数据处理页：非破坏性操作管道。"""

    project_modified = Signal()  # 操作链保存等操作导致项目修改时发出
    assets_modified = Signal()   # 全局 Pipeline 模板变更时发出

    def __init__(self, parent=None):
        super().__init__(parent)
        self._extension_panel_visible = False
        self._extension_panel_width = 360
        self._src_xs: List[float] = []
        self._src_ys: List[float] = []
        self._out_xs: List[float] = []
        self._out_ys: List[float] = []
        self._src_series_batch: List[DataSeries] = []
        self._out_series_batch: List[DataSeries] = []
        self._ops: List[Dict[str, Any]] = []
        self._param_widgets: List[_ParamWidget] = []
        self._processing_op_labels: List[str] = list(_OP_LABELS)
        self._processing_op_types: List[str] = list(_OP_TYPES)
        self._processing_op_hints: Dict[str, str] = dict(_OP_HINTS)
        self._processing_extension_options: Dict[str, Dict[str, Any]] = {}
        self._selected_src_id: Optional[str] = None
        self._selected_source_kind: Optional[str] = None
        self._selected_source_node_id: Optional[str] = None
        self._current_pipeline_id: Optional[str] = None
        self._pipeline_template_ids: List[str] = []
        self._save_target_ids: List[Optional[str]] = []
        # 防抖定时器：参数变更时防止每次按键都触发管道计算
        self._run_timer = QTimer(self)
        self._run_timer.setSingleShot(True)
        self._run_timer.setInterval(300)
        self._run_timer.timeout.connect(self._run_pipeline_now)
        self._shortcut_bindings = ShortcutBindingSet()
        self._setup_ui()
        self._setup_shortcuts()
        self._refresh_tree()
        self._onboarding_controller = PageOnboardingController(self, "process", self._process_onboarding_steps)

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
        self._content_splitter.addWidget(self._build_middle())
        self._content_splitter.addWidget(self._build_right())
        self._content_splitter.setSizes([360, 620])
        self._page_splitter.addWidget(self._content_splitter)

        self._extension_panel = ExtensionConfigPanel("处理扩展", "应用扩展", self)
        self._extension_panel.set_context("数据处理", "当前操作链")
        self._extension_panel.set_status_context("processing", "处理扩展")
        self._extension_panel.apply_requested.connect(self._on_processing_extension_apply)
        self._extension_panel.reload_requested.connect(self._reload_processing_extensions)
        self._extension_panel.setMinimumWidth(self._extension_panel_width)
        self._extension_panel.setMaximumWidth(self._extension_panel_width)
        self._page_splitter.addWidget(self._extension_panel)
        self._page_splitter.setStretchFactor(0, 1)
        self._page_splitter.setStretchFactor(1, 0)
        self._refresh_processing_extensions()
        self.set_extension_panel_visible(self._extension_panel_visible)
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
                "从共享树双击数据后，这里会同步当前处理对象。",
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
        mv.addWidget(make_section_label("操作链"))

        self._current_input_label = BodyLabel("当前输入: 未选择")
        self._current_input_label.setWordWrap(True)
        mv.addWidget(self._current_input_label)

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
        mv.addLayout(template_row)

        self._op_list = ListWidget(self)
        self._op_list.currentRowChanged.connect(self._on_op_selected)
        mv.addWidget(self._op_list, stretch=1)

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
        mv.addLayout(btn_row)

        for widget in (self._add_op_combo, add_btn, del_btn, up_btn, dn_btn, load_tpl_btn,
                       save_as_btn, overwrite_btn, clear_ops_btn):
            _install_fluent_tip(widget, widget.toolTip() or self._add_op_combo.toolTip(), ToolTipPosition.BOTTOM)

        mv.addWidget(make_hsep())
        mv.addWidget(make_section_label("操作参数"))
        self._param_stack = QStackedWidget(self)
        mv.addWidget(self._param_stack)
        mv.addStretch()

        mv.addWidget(make_hsep())
        mv.addWidget(make_section_label("导出为数据列"))

        export_hint = BodyLabel("导出时会先命名，并选择或新建目标数据文件。", self)
        export_hint.setWordWrap(True)
        export_hint.hide()
        mv.addWidget(export_hint)

        self._save_name_edit = LineEdit(self)
        self._save_name_edit.setPlaceholderText("processed_result")
        self._save_target_combo = ComboBox(self)
        self._save_name_edit.hide()
        self._save_target_combo.hide()

        mv.addWidget(make_hsep())
        self._save_result_button = PrimaryPushButton(FIF.SAVE, "导出为数据列")
        self._save_result_button.clicked.connect(self._save_result)
        apply_button_metrics(self._save_result_button, min_width=WORKBENCH_BUTTON_MIN_WIDTH)
        mv.addWidget(self._save_result_button)
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
            self._canvas.setMinimumHeight(260)
            rv.addWidget(self._canvas, stretch=1)
        else:
            self._figure = None
            self._canvas = None
            rv.addWidget(BodyLabel("需要 matplotlib"), stretch=1)
        self._stats_label = BodyLabel("（选择数据并配置操作后显示统计）")
        self._stats_label.setWordWrap(True)
        rv.addWidget(self._stats_label)
        return panel

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
        for ds in p.datasets:
            for s in ds.series:
                if s.x:
                    it = QTreeWidgetItem([f"  {ds.name} / {s.name}"])
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

    def _set_source_from_tree_node(self, kind: str, node_id: str) -> bool:
        if kind == "data_file":
            source_series = [series for series in project_manager.get_all_series_from_node(kind, node_id) if series and series.x]
            if not source_series:
                return False
            node = project_manager.get_node_by_id(node_id)
            source_name = node.name if node is not None else source_series[0].name
            self._src_series_batch = list(source_series)
            self._src_xs = list(source_series[0].x)
            self._src_ys = list(source_series[0].y)
            self._selected_src_id = source_series[0].id
            self._current_input_label.setText(f"当前输入: {source_name}（共 {len(source_series)} 条数据系列）")
            self._extension_panel.set_context("数据处理", source_name)
            self._save_name_edit.setText(self._suggest_result_name(source_name))
            self._refresh_save_targets()
            self._update_save_action_presentation()
            self._run_pipeline()
            return True

        series = project_manager.get_series_from_node(kind, node_id)
        if series is None or not series.x:
            return False
        self._src_series_batch = [series]
        self._src_xs = list(series.x)
        self._src_ys = list(series.y)
        self._selected_src_id = series.id
        self._current_input_label.setText(f"当前输入: {series.name}")
        self._extension_panel.set_context("数据处理", series.name)
        self._save_name_edit.setText(self._suggest_result_name(series.name))
        self._refresh_save_targets()
        self._update_save_action_presentation()
        self._run_pipeline()
        return True

    def _is_data_file_input(self) -> bool:
        return self._selected_source_kind == "data_file" and bool(self._src_series_batch)

    def _update_save_action_presentation(self) -> None:
        self._save_result_button.setText("导出为数据文件" if self._is_data_file_input() else "导出为数据列")

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
        self._save_name_edit.setText(self._suggest_result_name())
        self._run_pipeline()

    def _add_op(self):
        idx = self._add_op_combo.currentIndex()
        if not (0 <= idx < len(self._processing_op_types)):
            return
        op_type = self._processing_op_types[idx]
        self._add_operation_to_chain(op_type, self._default_params_for_processing_type(op_type))

    def _add_operation_to_chain(self, op_type: str, params: Optional[Dict[str, Any]] = None) -> None:
        op_label = self._op_label_for_type(op_type)
        pw = _make_param_widget(op_type, self, self._run_pipeline)
        if params and hasattr(pw, "set_params"):
            pw.set_params(dict(params))
        self._param_widgets.append(pw)
        self._param_stack.addWidget(pw)
        self._ops.append({"type": op_type, "params": pw.get_params()})
        self._op_list.addItem(op_label)
        self._op_list.setCurrentRow(len(self._ops) - 1)
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

    # ─────────────────────────────────────────────────────────
    # 管道执行 + 预览
    # ─────────────────────────────────────────────────────────

    def _run_pipeline(self):
        """防抖入口：重置 300ms 计时器，停止高频连续触发。"""
        self._run_timer.start()

    def _run_pipeline_now(self):
        if not self._src_series_batch:
            return
        for op, pw in zip(self._ops, self._param_widgets):
            op["params"] = pw.get_params()
        try:
            self._out_series_batch = []
            for source_series in self._src_series_batch:
                out_xs, out_ys = apply_pipeline(list(source_series.x), list(source_series.y), self._ops)
                self._out_series_batch.append(DataSeries(
                    name=source_series.name,
                    x=list(out_xs),
                    y=list(out_ys),
                    x_label=source_series.x_label,
                    y_label=source_series.y_label,
                    color=source_series.color,
                    visible=source_series.visible,
                    source="computed",
                    source_curve_id=source_series.source_curve_id,
                ))
            preview_series = self._out_series_batch[0] if self._out_series_batch else None
            self._out_xs = list(preview_series.x) if preview_series is not None else []
            self._out_ys = list(preview_series.y) if preview_series is not None else []
        except Exception as e:
            self._out_series_batch = []
            self._out_xs = []
            self._out_ys = []
            self._stats_label.setText(f"⚠ 处理错误: {e}")
            return
        self._draw_preview()
        self._update_stats()

    def _draw_preview(self):
        if not _HAS_MPL or self._figure is None:
            return
        self._figure.clear()
        ax = self._figure.add_subplot(111)
        dark = isDarkTheme()
        bg = "#1e1e1e" if dark else "#ffffff"
        fg = "#cccccc" if dark else "#222222"
        gc = "#444444" if dark else "#dddddd"
        self._apply_preview_host_background()
        self._figure.patch.set_facecolor(bg)
        ax.set_facecolor(bg)
        ax.tick_params(colors=fg, labelcolor=fg)
        for sp in ax.spines.values():
            sp.set_edgecolor(fg)
        ax.grid(True, color=gc, linestyle="--", linewidth=0.5, alpha=0.6)
        _MAX_PTS = 2000
        src_label = "原始（预览第一条）" if len(self._src_series_batch) > 1 else "原始"
        out_label = "处理后（预览第一条）" if len(self._out_series_batch) > 1 else "处理后"
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
        background = "#1e1e1e" if isDarkTheme() else "#ffffff"
        self._canvas.setStyleSheet(f"background: {background};")

    def _update_stats(self):
        n = len(self._out_ys)
        if n == 0:
            self._stats_label.setText("输出为空")
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
        self._stats_label.setText(
            f"{prefix}输出 N={n}  Y: [{y_min:.4g}, {y_max:.4g}]  均值={mean:.4g}  σ={std:.4g}")

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

        default_name = self._save_name_edit.text().strip() or self._suggest_result_name()
        preferred_target_node_id = self._selected_source_node_id if self._is_data_file_input() else None
        export_plan = choose_data_export_plan(
            self,
            title="导出为数据文件" if self._is_data_file_input() else "导出为数据列",
            default_export_name=default_name,
            default_file_name=f"{default_name}.process",
            preferred_target_node_id=preferred_target_node_id,
            file_suffix=".process",
            allow_append_to_existing=not self._is_data_file_input(),
            show_export_name=not self._is_data_file_input(),
        )
        if export_plan is None:
            return
        if self._is_data_file_input():
            if export_plan.target_data_file_id:
                InfoBar.warning("提示", "整份数据文件结果只能另存为新的数据文件", parent=self, position=InfoBarPosition.TOP)
                return
            data_file = DataFile(
                name=export_plan.new_data_file_name or f"{default_name}.process",
                series=[
                    DataSeries(
                        name=series.name,
                        x=list(series.x),
                        y=list(series.y),
                        x_label=series.x_label,
                        y_label=series.y_label,
                        color=series.color,
                        visible=series.visible,
                        source="computed",
                        source_curve_id=series.source_curve_id,
                    )
                    for series in self._out_series_batch
                ],
            )
            node = project_manager.add_data_file(data_file, parent_id=export_plan.new_parent_id)
            if node is None:
                message = project_manager.get_last_error_message() or "未能创建处理结果数据文件"
                InfoBar.error("保存失败", message, parent=self, position=InfoBarPosition.TOP)
                return
            message = f"{len(data_file.series)} 条数据系列 -> {data_file.name}"
        else:
            result_name = export_plan.export_name
            self._save_name_edit.setText(result_name)
            series = DataSeries(
                name=result_name,
                x=list(self._out_xs),
                y=list(self._out_ys),
                source="computed",
            )
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
        if not base_name and self._selected_source_kind == "data_file" and self._selected_source_node_id:
            node = project_manager.get_node_by_id(self._selected_source_node_id)
            base_name = node.name if node is not None else None
        if not base_name and self._selected_src_id:
            series = project_manager.get_series_from_node("series", self._selected_src_id)
            base_name = series.name if series is not None else None
        if not base_name:
            base_name = "processed"
        op_suffix = "_".join(op["type"] for op in self._ops[:3])
        return f"{base_name}_{op_suffix}" if op_suffix else base_name

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

    def _processing_extension_entries(self) -> List[dict]:
        return [build_extension_entry(extension) for extension in extension_registry.list_processing()]

    def _refresh_processing_extensions(self) -> None:
        current_type = None
        if hasattr(self, "_add_op_combo"):
            idx = self._add_op_combo.currentIndex()
            if 0 <= idx < len(self._processing_op_types):
                current_type = self._processing_op_types[idx]
        self._processing_op_labels = list(_OP_LABELS)
        self._processing_op_types = list(_OP_TYPES)
        self._processing_op_hints = dict(_OP_HINTS)
        for extension in extension_registry.list_processing():
            self._processing_op_labels.append(f"扩展 · {extension.name}")
            self._processing_op_types.append(extension.type)
            self._processing_op_hints[extension.type] = extension.description or f"自定义处理扩展：{extension.name}"
        if hasattr(self, "_add_op_combo"):
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

    def _reload_processing_extensions(self) -> None:
        report = reload_builtin_extensions()
        self._refresh_processing_extensions()
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
        if op_type in _OP_TYPE_TO_LABEL:
            return _OP_TYPE_TO_LABEL[op_type]
        extension = extension_registry.get_processing(op_type)
        if extension is not None:
            return f"扩展 · {extension.name}"
        return op_type or "?"

    def _default_params_for_processing_type(self, op_type: str) -> Dict[str, Any]:
        extension = extension_registry.get_processing(op_type)
        if extension is None:
            return {}
        return dict(self._processing_extension_options.get(op_type, extension.default_options))

    def _set_add_op_combo_type(self, op_type: str) -> None:
        if op_type not in self._processing_op_types:
            return
        self._add_op_combo.setCurrentIndex(self._processing_op_types.index(op_type))

    def _on_processing_extension_apply(self, type_id: str, options: Dict[str, Any]) -> None:
        self._processing_extension_options[type_id] = dict(options)
        self._set_add_op_combo_type(type_id)
        self._add_operation_to_chain(type_id, options)
        InfoBar.success("已添加", f"扩展 {self._op_label_for_type(type_id)} 已加入操作链", parent=self, position=InfoBarPosition.TOP)

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
        self._selected_source_kind = data_type
        self._selected_source_node_id = obj_id
        if self._set_source_from_tree_node(data_type, obj_id):
            return
        self._selected_src_id = None
        self._src_series_batch = []
        self._out_series_batch = []
        self._src_xs = []
        self._src_ys = []
        self._out_xs = []
        self._out_ys = []
        self._current_input_label.setText("当前输入: 未选择")
        self._save_name_edit.clear()
        self._update_save_action_presentation()
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

    def on_tree_node_selected(self, kind: str, node_id: str) -> None:
        """共享树选中节点 → 加载为处理输入（series / data_file / image_work / curve）。"""
        if kind in ("series", "curve", "data_file", "image_work"):
            self.receive_data(kind, node_id)

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
        for op in ops:
            op_type = op.get("type", "")
            params = dict(op.get("params", {}))
            self._ops.append({"type": op_type, "params": params})
            if extension_registry.get_processing(op_type) is not None:
                self._processing_extension_options[op_type] = dict(params)
            self._op_list.addItem(self._op_label_for_type(op_type))
            widget = _make_param_widget(op_type, self, self._run_pipeline)
            if hasattr(widget, "set_params"):
                widget.set_params(params)
            self._param_widgets.append(widget)
            self._param_stack.addWidget(widget)
        if self._ops:
            self._op_list.setCurrentRow(len(self._ops) - 1)
            self._on_op_selected(len(self._ops) - 1)
        self._save_name_edit.setText(self._suggest_result_name())
        if self._ops:
            self._run_pipeline()

    def update_theme(self):
        if self._out_xs:
            self._draw_preview()


# ─────────────────────────────────────────────────────────────
# 参数控件
# ─────────────────────────────────────────────────────────────

class _ParamWidget(QWidget):
    def get_params(self) -> dict:
        return {}

    def set_params(self, params: dict) -> None:
        del params


class _CropParam(_ParamWidget):
    def __init__(self, parent, on_change):
        super().__init__(parent)
        lv = QVBoxLayout(self)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(4)
        r1 = QHBoxLayout()
        r1.addWidget(BodyLabel("X min:"))
        self._min = LineEdit()
        self._min.setPlaceholderText("-∞")
        self._min.textChanged.connect(on_change)
        _install_fluent_tip(self._min, "裁剪后的最小 X，留空表示不限制")
        r1.addWidget(self._min)
        lv.addLayout(r1)
        r2 = QHBoxLayout()
        r2.addWidget(BodyLabel("X max:"))
        self._max = LineEdit()
        self._max.setPlaceholderText("+∞")
        self._max.textChanged.connect(on_change)
        _install_fluent_tip(self._max, "裁剪后的最大 X，留空表示不限制")
        r2.addWidget(self._max)
        lv.addLayout(r2)

    def get_params(self):
        def _f(e, default):
            try: return float(e.text())
            except: return default
        return {"x_min": _f(self._min, -math.inf), "x_max": _f(self._max, math.inf)}

    def set_params(self, params: dict) -> None:
        x_min = params.get("x_min")
        x_max = params.get("x_max")
        self._min.setText("" if x_min in (None, -math.inf) else str(x_min))
        self._max.setText("" if x_max in (None, math.inf) else str(x_max))


class _SmoothParam(_ParamWidget):
    def __init__(self, parent, on_change):
        super().__init__(parent)
        lv = QVBoxLayout(self)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(4)
        r1 = QHBoxLayout()
        r1.addWidget(BodyLabel("方法:"))
        self._method = ComboBox()
        self._method.addItems(["savgol", "moving_avg"])
        self._method.currentIndexChanged.connect(on_change)
        _install_fluent_tip(self._method, "选择平滑算法：Savitzky-Golay 或移动平均")
        r1.addWidget(self._method, 1)
        lv.addLayout(r1)
        r2 = QHBoxLayout()
        r2.addWidget(BodyLabel("窗口:"))
        self._window = LineEdit()
        self._window.setText("11")
        self._window.textChanged.connect(on_change)
        _install_fluent_tip(self._window, "平滑窗口大小，通常取奇数")
        r2.addWidget(self._window)
        r2.addWidget(BodyLabel("多项式:"))
        self._poly = LineEdit()
        self._poly.setText("3")
        self._poly.textChanged.connect(on_change)
        _install_fluent_tip(self._poly, "Savitzky-Golay 多项式阶数")
        r2.addWidget(self._poly)
        lv.addLayout(r2)

    def get_params(self):
        def _i(e, d):
            try: return max(1, int(e.text()))
            except: return d
        return {"method": self._method.currentText(),
                "window": _i(self._window, 11), "poly": _i(self._poly, 3)}

    def set_params(self, params: dict) -> None:
        method = params.get("method", "savgol")
        idx = self._method.findText(method)
        if idx >= 0:
            self._method.setCurrentIndex(idx)
        self._window.setText(str(params.get("window", 11)))
        self._poly.setText(str(params.get("poly", 3)))


class _NormalizeParam(_ParamWidget):
    def __init__(self, parent, on_change):
        super().__init__(parent)
        lv = QHBoxLayout(self)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(BodyLabel("模式:"))
        self._mode = ComboBox()
        self._mode.addItems(["minmax", "zscore"])
        self._mode.currentIndexChanged.connect(on_change)
        _install_fluent_tip(self._mode, "minmax 映射到 [0,1]；zscore 转为标准分数")
        lv.addWidget(self._mode, 1)

    def get_params(self):
        return {"mode": self._mode.currentText()}

    def set_params(self, params: dict) -> None:
        mode = params.get("mode", "minmax")
        idx = self._mode.findText(mode)
        if idx >= 0:
            self._mode.setCurrentIndex(idx)


class _ResampleParam(_ParamWidget):
    def __init__(self, parent, on_change):
        super().__init__(parent)
        lv = QVBoxLayout(self)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(4)
        mode_row = QHBoxLayout()
        mode_row.addWidget(BodyLabel("方式:"))
        self._mode = ComboBox()
        self._mode.addItems(["点数", "间距"])
        self._mode.currentIndexChanged.connect(self._sync_mode)
        self._mode.currentIndexChanged.connect(on_change)
        _install_fluent_tip(self._mode, "可按输出点数或固定 X 间距重采样")
        mode_row.addWidget(self._mode, 1)
        lv.addLayout(mode_row)

        value_row = QHBoxLayout()
        self._value_label = BodyLabel("点数:")
        value_row.addWidget(self._value_label)
        self._value_edit = LineEdit()
        self._value_edit.setText("200")
        self._value_edit.textChanged.connect(on_change)
        value_row.addWidget(self._value_edit)
        lv.addLayout(value_row)
        self._sync_mode()

    def _sync_mode(self) -> None:
        if self._mode.currentIndex() == 1:
            self._value_label.setText("间距:")
            self._value_edit.setPlaceholderText("0.1")
            _install_fluent_tip(self._value_edit, "输出相邻点之间的 X 间距")
        else:
            self._value_label.setText("点数:")
            self._value_edit.setPlaceholderText("200")
            _install_fluent_tip(self._value_edit, "输出重采样后的点数")

    def get_params(self):
        if self._mode.currentIndex() == 1:
            try:
                step = float(self._value_edit.text())
            except Exception:
                step = 0.1
            return {"mode": "spacing", "step": max(1e-9, step)}
        try:
            n = int(float(self._value_edit.text()))
        except Exception:
            n = 200
        return {"mode": "count", "n": max(2, n)}

    def set_params(self, params: dict) -> None:
        mode = str(params.get("mode", "count") or "count").strip().lower()
        self._mode.setCurrentIndex(1 if mode == "spacing" else 0)
        if mode == "spacing":
            self._value_edit.setText(str(params.get("step", params.get("spacing", 0.1))))
        else:
            self._value_edit.setText(str(params.get("n", 200)))
        self._sync_mode()


class _FFTParam(_ParamWidget):
    def __init__(self, parent, on_change):
        super().__init__(parent)
        lv = QVBoxLayout(self)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(4)
        r1 = QHBoxLayout()
        r1.addWidget(BodyLabel("输出:"))
        self._output = ComboBox()
        self._output.addItems(["幅值谱", "功率谱"])
        self._output.currentIndexChanged.connect(on_change)
        _install_fluent_tip(self._output, "选择 FFT 输出为幅值谱还是功率谱")
        r1.addWidget(self._output, 1)
        lv.addLayout(r1)
        self._detrend = CheckBox("先去均值")
        self._detrend.setChecked(True)
        self._detrend.stateChanged.connect(on_change)
        _install_fluent_tip(self._detrend, "在 FFT 前减去均值，减弱直流分量影响")
        lv.addWidget(self._detrend)

        r2 = QHBoxLayout()
        r2.addWidget(BodyLabel("采样频率:"))
        self._sample_rate = LineEdit()
        self._sample_rate.setPlaceholderText("留空则按 X 间隔自动估计")
        self._sample_rate.textChanged.connect(on_change)
        _install_fluent_tip(self._sample_rate, "可选；指定后按该采样频率计算 FFT 频轴")
        r2.addWidget(self._sample_rate, 1)
        lv.addLayout(r2)
        lv.addWidget(BodyLabel("留空时，频率步长将根据 X 轴间隔自动估计"))

    def get_params(self):
        try:
            sample_rate = float(self._sample_rate.text().strip()) if self._sample_rate.text().strip() else None
        except Exception:
            sample_rate = None
        return {
            "output": "power" if self._output.currentIndex() == 1 else "amplitude",
            "detrend": self._detrend.isChecked(),
            "sampling_rate": sample_rate,
        }

    def set_params(self, params: dict) -> None:
        self._output.setCurrentIndex(1 if params.get("output") == "power" else 0)
        self._detrend.setChecked(bool(params.get("detrend", True)))
        sample_rate = params.get("sampling_rate")
        self._sample_rate.setText("" if sample_rate in (None, "") else str(sample_rate))


class _EmptyParam(_ParamWidget):
    def __init__(self, parent, on_change):
        super().__init__(parent)
        lv = QVBoxLayout(self)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(BodyLabel("（无需配置参数）"))

    def get_params(self):
        return {}


class _IntegralParam(_ParamWidget):
    def __init__(self, parent, on_change):
        super().__init__(parent)
        lv = QVBoxLayout(self)
        lv.setContentsMargins(0, 0, 0, 0)
        self._cum = CheckBox("累积积分")
        self._cum.setChecked(True)
        self._cum.stateChanged.connect(on_change)
        _install_fluent_tip(self._cum, "勾选后输出从起点开始的累积积分；取消则输出总积分")
        lv.addWidget(self._cum)

    def get_params(self):
        return {"cumulative": self._cum.isChecked()}

    def set_params(self, params: dict) -> None:
        self._cum.setChecked(bool(params.get("cumulative", True)))


class _TransformParam(_ParamWidget):
    def __init__(self, parent, on_change):
        super().__init__(parent)
        lv = QVBoxLayout(self)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(4)
        lv.addWidget(BodyLabel("X 表达式（留空不变）:"))
        self._x_expr = LineEdit()
        self._x_expr.setPlaceholderText("例：x / 1000")
        self._x_expr.textChanged.connect(on_change)
        _install_fluent_tip(self._x_expr, "可用 x、y、math、sqrt、log、sin、cos、pi、e")
        lv.addWidget(self._x_expr)
        lv.addWidget(BodyLabel("Y 表达式（留空不变）:"))
        self._y_expr = LineEdit()
        self._y_expr.setPlaceholderText("例：y * 2 + 1")
        self._y_expr.textChanged.connect(on_change)
        _install_fluent_tip(self._y_expr, "可用 x、y、math、sqrt、log、sin、cos、pi、e")
        lv.addWidget(self._y_expr)
        lv.addWidget(BodyLabel("可用：x, y, math, sqrt, log, sin, cos, pi, e"))

    def get_params(self):
        return {"x_expr": self._x_expr.text().strip(), "y_expr": self._y_expr.text().strip()}

    def set_params(self, params: dict) -> None:
        self._x_expr.setText(params.get("x_expr", ""))
        self._y_expr.setText(params.get("y_expr", ""))


class _FilterParam(_ParamWidget):
    def __init__(self, parent, on_change):
        super().__init__(parent)
        lv = QVBoxLayout(self)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(4)
        r0 = QHBoxLayout()
        r0.addWidget(BodyLabel("滤波类型:"))
        self._mode = ComboBox()
        self._mode.addItems(["低通", "高通"])
        self._mode.currentIndexChanged.connect(on_change)
        _install_fluent_tip(self._mode, "低通保留低频，高通保留高频")
        r0.addWidget(self._mode)
        lv.addLayout(r0)
        r1 = QHBoxLayout()
        r1.addWidget(BodyLabel("频率方式:"))
        self._cutoff_mode = ComboBox()
        self._cutoff_mode.addItems(["归一化", "实际频率"])
        self._cutoff_mode.currentIndexChanged.connect(self._sync_cutoff_mode)
        self._cutoff_mode.currentIndexChanged.connect(on_change)
        _install_fluent_tip(self._cutoff_mode, "归一化频率范围 (0,1)；实际频率会按采样频率换算")
        r1.addWidget(self._cutoff_mode)
        lv.addLayout(r1)

        r2 = QHBoxLayout()
        self._cutoff_label = BodyLabel("截止频率:")
        r2.addWidget(self._cutoff_label)
        self._cutoff = LineEdit()
        self._cutoff.setText("0.1")
        self._cutoff.textChanged.connect(on_change)
        r2.addWidget(self._cutoff)
        lv.addLayout(r2)

        r3 = QHBoxLayout()
        r3.addWidget(BodyLabel("采样频率:"))
        self._sample_rate = LineEdit()
        self._sample_rate.setPlaceholderText("留空则按 X 间隔自动估计")
        self._sample_rate.textChanged.connect(on_change)
        _install_fluent_tip(self._sample_rate, "实际频率模式下可选；留空则按 X 间隔自动估计")
        r3.addWidget(self._sample_rate)
        lv.addLayout(r3)

        r4 = QHBoxLayout()
        r4.addWidget(BodyLabel("阶数:"))
        self._order = LineEdit()
        self._order.setText("4")
        self._order.textChanged.connect(on_change)
        _install_fluent_tip(self._order, "Butterworth 滤波器阶数")
        r4.addWidget(self._order)
        lv.addLayout(r4)
        self._hint_label = BodyLabel("")
        lv.addWidget(self._hint_label)
        self._sync_cutoff_mode()

    def _sync_cutoff_mode(self) -> None:
        actual_mode = self._cutoff_mode.currentIndex() == 1
        if actual_mode:
            self._cutoff_label.setText("截止频率:")
            self._cutoff.setPlaceholderText("例如 10")
            self._hint_label.setText("实际频率模式：截止频率将按采样频率换算到 Nyquist")
            _install_fluent_tip(self._cutoff, "输入与采样频率同单位的截止频率")
        else:
            self._cutoff_label.setText("截止频率:")
            self._cutoff.setPlaceholderText("0.1")
            self._hint_label.setText("归一化频率范围 (0, 1)，1 = Nyquist")
            _install_fluent_tip(self._cutoff, "归一化截止频率，范围 (0, 1)，1 表示 Nyquist")

    def get_params(self):
        def _f(e, d):
            try: return float(e.text())
            except: return d
        def _i(e, d):
            try: return max(1, int(e.text()))
            except: return d
        mode = "high" if self._mode.currentIndex() == 1 else "low"
        sample_rate_text = self._sample_rate.text().strip()
        try:
            sample_rate = float(sample_rate_text) if sample_rate_text else None
        except Exception:
            sample_rate = None
        return {
            "cutoff": _f(self._cutoff, 0.1),
            "order": _i(self._order, 4),
            "mode": mode,
            "cutoff_mode": "actual" if self._cutoff_mode.currentIndex() == 1 else "normalized",
            "sampling_rate": sample_rate,
        }

    def set_params(self, params: dict) -> None:
        self._cutoff.setText(str(params.get("cutoff", 0.1)))
        self._order.setText(str(params.get("order", 4)))
        mode = params.get("mode", "low")
        self._mode.setCurrentIndex(1 if mode == "high" else 0)
        cutoff_mode = str(params.get("cutoff_mode", "normalized") or "normalized").strip().lower()
        self._cutoff_mode.setCurrentIndex(1 if cutoff_mode == "actual" else 0)
        sample_rate = params.get("sampling_rate")
        self._sample_rate.setText("" if sample_rate in (None, "") else str(sample_rate))
        self._sync_cutoff_mode()


class _JsonParam(_ParamWidget):
    def __init__(self, parent, on_change, *, description: str = "", default_params: Optional[dict] = None):
        super().__init__(parent)
        self._last_valid = dict(default_params or {})
        lv = QVBoxLayout(self)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(4)
        if description:
            label = BodyLabel(description, self)
            label.setWordWrap(True)
            lv.addWidget(label)
        self._editor = PlainTextEdit(self)
        self._editor.setPlaceholderText('{\n  "option": "value"\n}')
        self._editor.setFixedHeight(180)
        self._editor.textChanged.connect(on_change)
        lv.addWidget(self._editor)
        self.set_params(self._last_valid)

    def get_params(self) -> dict:
        text = self._editor.toPlainText().strip() or "{}"
        try:
            data = json.loads(text)
        except Exception:
            return dict(self._last_valid)
        if not isinstance(data, dict):
            return dict(self._last_valid)
        self._last_valid = dict(data)
        return dict(self._last_valid)

    def set_params(self, params: dict) -> None:
        self._last_valid = dict(params or {})
        self._editor.setPlainText(json.dumps(self._last_valid, ensure_ascii=False, indent=2))


def _make_param_widget(op_type: str, parent, on_change) -> _ParamWidget:
    m = {
        "crop":       _CropParam,
        "smooth":     _SmoothParam,
        "normalize":  _NormalizeParam,
        "resample":   _ResampleParam,
        "fft":        _FFTParam,
        "derivative": _EmptyParam,
        "integral":   _IntegralParam,
        "transform":  _TransformParam,
        "filter":     _FilterParam,
    }
    widget_cls = m.get(op_type)
    if widget_cls is not None:
        return widget_cls(parent, on_change)
    extension = extension_registry.get_processing(op_type)
    if extension is not None:
        return _JsonParam(
            parent,
            on_change,
            description=extension.description,
            default_params=extension.default_options,
        )
    return _EmptyParam(parent, on_change)
