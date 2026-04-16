"""数据处理页

三列布局：左侧数据选择 | 中间操作链 | 右侧效果预览
支持非破坏性操作管道，结果可另存为新数据系列。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout,
    QInputDialog, QSplitter, QStackedWidget, QVBoxLayout, QWidget, QTreeWidgetItem,
)
from qfluentwidgets import (
    BodyLabel, ComboBox, FluentIcon as FIF,
    InfoBar, InfoBarPosition, LineEdit,
    PrimaryPushButton, ToolButton,
    TreeWidget, ListWidget, CheckBox,
)

from ui.theme import make_section_label, make_hsep
from core.project_manager import project_manager
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
    ("求导 (Derivative)",      "derivative"),
    ("积分 (Integral)",        "integral"),
    ("变换表达式 (Transform)", "transform"),
    ("低通滤波 (Filter)",      "filter"),
]
_OP_LABELS = [o[0] for o in _OPS]
_OP_TYPES  = [o[1] for o in _OPS]


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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._src_xs: List[float] = []
        self._src_ys: List[float] = []
        self._out_xs: List[float] = []
        self._out_ys: List[float] = []
        self._ops: List[Dict[str, Any]] = []
        self._param_widgets: List[_ParamWidget] = []
        self._selected_src_id: Optional[str] = None
        self._current_pipeline_id: Optional[str] = None
        self._pipeline_template_ids: List[str] = []
        # 防抖定时器：参数变更时防止每次按键都触发管道计算
        self._run_timer = QTimer(self)
        self._run_timer.setSingleShot(True)
        self._run_timer.setInterval(300)
        self._run_timer.timeout.connect(self._run_pipeline_now)
        self._setup_ui()
        self._refresh_tree()

    # ─────────────────────────────────────────────────────────
    # UI 构建
    # ─────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)
        root.addWidget(splitter)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_middle())
        splitter.addWidget(self._build_right())
        splitter.setSizes([240, 300, 460])

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
        panel = QWidget()
        panel.setMinimumWidth(260)
        panel.setMaximumWidth(380)
        mv = QVBoxLayout(panel)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(6)
        mv.addWidget(make_section_label("操作链"))

        template_row = QHBoxLayout()
        self._pipeline_combo = ComboBox(self)
        template_row.addWidget(self._pipeline_combo, 1)
        load_tpl_btn = ToolButton(FIF.FOLDER)
        load_tpl_btn.setToolTip("加载模板")
        load_tpl_btn.clicked.connect(self._load_pipeline_from_combo)
        template_row.addWidget(load_tpl_btn)
        save_as_btn = ToolButton(FIF.ADD)
        save_as_btn.setToolTip("另存为模板")
        save_as_btn.clicked.connect(self._on_save_pipeline_template_as)
        template_row.addWidget(save_as_btn)
        overwrite_btn = ToolButton(FIF.SAVE)
        overwrite_btn.setToolTip("覆盖当前模板")
        overwrite_btn.clicked.connect(self._overwrite_current_pipeline)
        template_row.addWidget(overwrite_btn)
        mv.addLayout(template_row)

        self._op_list = ListWidget(self)
        self._op_list.currentRowChanged.connect(self._on_op_selected)
        mv.addWidget(self._op_list, stretch=1)

        btn_row = QHBoxLayout()
        self._add_op_combo = ComboBox(self)
        self._add_op_combo.addItems(_OP_LABELS)
        btn_row.addWidget(self._add_op_combo, 1)
        add_btn = ToolButton(FIF.ADD)
        add_btn.setToolTip("添加操作")
        add_btn.clicked.connect(self._add_op)
        btn_row.addWidget(add_btn)
        del_btn = ToolButton(FIF.DELETE)
        del_btn.setToolTip("删除选中操作")
        del_btn.clicked.connect(self._remove_op)
        btn_row.addWidget(del_btn)
        up_btn = ToolButton(FIF.UP)
        up_btn.setToolTip("上移")
        up_btn.clicked.connect(self._move_op_up)
        btn_row.addWidget(up_btn)
        dn_btn = ToolButton(FIF.DOWN)
        dn_btn.setToolTip("下移")
        dn_btn.clicked.connect(self._move_op_down)
        btn_row.addWidget(dn_btn)
        mv.addLayout(btn_row)

        mv.addWidget(make_hsep())
        mv.addWidget(make_section_label("操作参数"))
        self._param_stack = QStackedWidget(self)
        mv.addWidget(self._param_stack)
        mv.addStretch()
        mv.addWidget(make_hsep())
        save_btn = PrimaryPushButton(FIF.SAVE, "另存为新系列")
        save_btn.clicked.connect(self._save_result)
        mv.addWidget(save_btn)
        self._refresh_pipeline_templates()
        return panel

    def _build_right(self) -> QWidget:
        panel = QWidget()
        rv = QVBoxLayout(panel)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(6)
        rv.addWidget(make_section_label("处理预览"))
        if _HAS_MPL:
            self._figure = Figure(figsize=(5, 4), tight_layout=True)
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
                self._src_xs = list(c.x_actual)
                self._src_ys = list(c.y_actual)
                self._selected_src_id = obj_id
        elif typ == "series":
            s = p.find_series(obj_id)
            if s:
                self._src_xs = list(s.x)
                self._src_ys = list(s.y)
                self._selected_src_id = obj_id
        self._run_pipeline()

    def _set_source_from_tree_node(self, kind: str, node_id: str) -> bool:
        series = project_manager.get_series_from_node(kind, node_id)
        if series is None or not series.x:
            return False
        self._src_xs = list(series.x)
        self._src_ys = list(series.y)
        self._selected_src_id = series.id
        self._run_pipeline()
        return True

    # ─────────────────────────────────────────────────────────
    # 操作链管理
    # ─────────────────────────────────────────────────────────

    def _add_op(self):
        idx = self._add_op_combo.currentIndex()
        op_type = _OP_TYPES[idx]
        op_label = _OP_LABELS[idx]
        pw = _make_param_widget(op_type, self, self._run_pipeline)
        self._param_widgets.append(pw)
        self._param_stack.addWidget(pw)
        self._ops.append({"type": op_type, "params": pw.get_params()})
        self._op_list.addItem(op_label)
        self._op_list.setCurrentRow(len(self._ops) - 1)
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
        if not self._src_xs:
            return
        for op, pw in zip(self._ops, self._param_widgets):
            op["params"] = pw.get_params()
        try:
            self._out_xs, self._out_ys = apply_pipeline(self._src_xs, self._src_ys, self._ops)
        except Exception as e:
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
        self._figure.patch.set_facecolor(bg)
        ax.set_facecolor(bg)
        ax.tick_params(colors=fg, labelcolor=fg)
        for sp in ax.spines.values():
            sp.set_edgecolor(fg)
        ax.grid(True, color=gc, linestyle="--", linewidth=0.5, alpha=0.6)
        _MAX_PTS = 2000
        if self._src_xs:
            sx, sy = _downsample(self._src_xs, self._src_ys, _MAX_PTS)
            ax.plot(sx, sy, color="#888888",
                    linestyle="--", linewidth=1.0, alpha=0.6, label="原始")
        if self._out_xs:
            ox, oy = _downsample(self._out_xs, self._out_ys, _MAX_PTS)
            ax.plot(ox, oy, color="#0078D4",
                    linewidth=1.5, label="处理后")
        if self._src_xs or self._out_xs:
            ax.legend(facecolor=bg, edgecolor=fg, labelcolor=fg, fontsize=8)
        self._canvas.draw()

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
        self._stats_label.setText(
            f"输出 N={n}  Y: [{y_min:.4g}, {y_max:.4g}]  均值={mean:.4g}  σ={std:.4g}")

    # ─────────────────────────────────────────────────────────
    # 保存结果
    # ─────────────────────────────────────────────────────────

    def _save_result(self):
        if not self._out_xs:
            InfoBar.warning("提示", "没有可保存的结果", parent=self, position=InfoBarPosition.TOP)
            return
        p = project_manager.current_project
        if p is None:
            InfoBar.warning("提示", "请先打开项目", parent=self, position=InfoBarPosition.TOP)
            return
        from models.schemas import DataSeries
        ops_str = "+".join(op["type"] for op in self._ops) or "processed"
        s = DataSeries(name=f"processed_{ops_str}", x=list(self._out_xs),
                       y=list(self._out_ys), source="computed")
        if not p.datasets:
            project_manager.add_dataset("处理结果")
        project_manager.add_series_to_dataset(p.datasets[-1].id, s)
        InfoBar.success("已保存", f"'{s.name}' → '{p.datasets[-1].name}'",
                        parent=self, position=InfoBarPosition.TOP)

    def _refresh_pipeline_templates(self) -> None:
        current_id = self._current_pipeline_id
        self._pipeline_combo.clear()
        self._pipeline_template_ids.clear()
        p = project_manager.current_project
        if p is None:
            return
        selected_index = -1
        for index, pipeline in enumerate(p.saved_pipelines):
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
        p = project_manager.current_project
        if p is None:
            return
        for node in p.tree.nodes if p.tree is not None else []:
            if node.kind == "pipeline" and node.pipeline_id == pipeline_id:
                self.load_pipeline(node.id)
                return

    def _save_pipeline_template_as_named(self, name: str) -> bool:
        clean_name = name.strip()
        if not clean_name:
            return False
        if not self._ops:
            return False
        sp = project_manager.add_saved_pipeline(clean_name, list(self._ops))
        if sp is None:
            return False
        self._current_pipeline_id = sp.id
        self._refresh_pipeline_templates()
        self.project_modified.emit()
        return True

    def _on_save_pipeline_template_as(self) -> None:
        if not self._ops:
            InfoBar.warning("提示", "当前没有可保存的处理链", parent=self, position=InfoBarPosition.TOP)
            return
        name, ok = QInputDialog.getText(self, "另存为 Pipeline 模板", "模板名称:")
        if not ok or not name.strip():
            return
        if self._save_pipeline_template_as_named(name):
            InfoBar.success("已保存", f"Pipeline 模板 {name.strip()} 已保存", parent=self, position=InfoBarPosition.TOP)

    def _overwrite_pipeline_template(self) -> bool:
        if not self._current_pipeline_id or not self._ops:
            return False
        updated = project_manager.update_saved_pipeline(self._current_pipeline_id, ops=list(self._ops))
        if updated:
            self.project_modified.emit()
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
        if self._set_source_from_tree_node(data_type, obj_id):
            self._shared_tree_hint.setText(f"当前输入来自共享树: {data_type} / {obj_id}")
            return
        self._refresh_tree()
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
        """从工具集加载 Pipeline 到当前操作链。"""
        p = project_manager.current_project
        if p is None or p.tree is None:
            return
        node = p.tree.get_node(node_id)
        if node is None or node.kind != "pipeline":
            return
        ops = project_manager.load_pipeline(node.pipeline_id)
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
            self._op_list.addItem(op_type or "?")
            widget = _make_param_widget(op_type, self, self._run_pipeline)
            if hasattr(widget, "set_params"):
                widget.set_params(params)
            self._param_widgets.append(widget)
            self._param_stack.addWidget(widget)
        if self._ops:
            self._op_list.setCurrentRow(len(self._ops) - 1)
            self._on_op_selected(len(self._ops) - 1)
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
        r1.addWidget(self._min)
        lv.addLayout(r1)
        r2 = QHBoxLayout()
        r2.addWidget(BodyLabel("X max:"))
        self._max = LineEdit()
        self._max.setPlaceholderText("+∞")
        self._max.textChanged.connect(on_change)
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
        r1.addWidget(self._method, 1)
        lv.addLayout(r1)
        r2 = QHBoxLayout()
        r2.addWidget(BodyLabel("窗口:"))
        self._window = LineEdit()
        self._window.setText("11")
        self._window.textChanged.connect(on_change)
        r2.addWidget(self._window)
        r2.addWidget(BodyLabel("多项式:"))
        self._poly = LineEdit()
        self._poly.setText("3")
        self._poly.textChanged.connect(on_change)
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
        lv = QHBoxLayout(self)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(BodyLabel("点数:"))
        self._n = LineEdit()
        self._n.setText("200")
        self._n.textChanged.connect(on_change)
        lv.addWidget(self._n)

    def get_params(self):
        try: return {"n": max(2, int(self._n.text()))}
        except: return {"n": 200}

    def set_params(self, params: dict) -> None:
        self._n.setText(str(params.get("n", 200)))


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
        lv.addWidget(self._x_expr)
        lv.addWidget(BodyLabel("Y 表达式（留空不变）:"))
        self._y_expr = LineEdit()
        self._y_expr.setPlaceholderText("例：y * 2 + 1")
        self._y_expr.textChanged.connect(on_change)
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
        r1 = QHBoxLayout()
        r1.addWidget(BodyLabel("截止频率:"))
        self._cutoff = LineEdit()
        self._cutoff.setText("0.1")
        self._cutoff.textChanged.connect(on_change)
        r1.addWidget(self._cutoff)
        lv.addLayout(r1)
        r2 = QHBoxLayout()
        r2.addWidget(BodyLabel("阶数:"))
        self._order = LineEdit()
        self._order.setText("4")
        self._order.textChanged.connect(on_change)
        r2.addWidget(self._order)
        lv.addLayout(r2)
        lv.addWidget(BodyLabel("截止频率范围 (0, 1)，1 = Nyquist"))

    def get_params(self):
        def _f(e, d):
            try: return float(e.text())
            except: return d
        def _i(e, d):
            try: return max(1, int(e.text()))
            except: return d
        return {"cutoff": max(0.001, min(0.999, _f(self._cutoff, 0.1))),
                "order": _i(self._order, 4)}

    def set_params(self, params: dict) -> None:
        self._cutoff.setText(str(params.get("cutoff", 0.1)))
        self._order.setText(str(params.get("order", 4)))


def _make_param_widget(op_type: str, parent, on_change) -> _ParamWidget:
    m = {
        "crop":       _CropParam,
        "smooth":     _SmoothParam,
        "normalize":  _NormalizeParam,
        "resample":   _ResampleParam,
        "derivative": _EmptyParam,
        "integral":   _IntegralParam,
        "transform":  _TransformParam,
        "filter":     _FilterParam,
    }
    return m.get(op_type, _EmptyParam)(parent, on_change)
