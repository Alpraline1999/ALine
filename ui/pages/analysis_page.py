"""分析页

布局：左侧配置（类型/已选数据/参数）| 右侧结果（图表 + 文本摘要 + 报告）
支持：曲线拟合、峰值检测、统计分析、相关性分析
新功能（v0.3）：通过共享项目树选择数据，Markdown 报告模板导出
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QListWidgetItem, QSplitter, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    BodyLabel, ComboBox, FluentIcon as FIF,
    InfoBar, InfoBarPosition, LineEdit,
    ListWidget, PrimaryPushButton, PushButton, ToolButton,
)

from ui.theme import make_section_label, make_hsep
from core.project_manager import project_manager

try:
    import matplotlib
    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    from qfluentwidgets import isDarkTheme
    _HAS_MPL = True
except Exception:
    _HAS_MPL = False

_ANALYSIS_TYPES = [
    ("曲线拟合",   "curve_fit"),
    ("峰值检测",   "peak_detect"),
    ("统计分析",   "statistics"),
    ("相关性分析", "correlation"),
]
_TYPE_LABELS = [t[0] for t in _ANALYSIS_TYPES]
_TYPE_IDS    = [t[1] for t in _ANALYSIS_TYPES]

_FIT_MODEL_LABELS = ["线性 (ax+b)", "幂函数 (a·x^b)", "指数 (a·e^(bx))",
                     "高斯", "2次多项式", "3次多项式"]
_FIT_MODEL_IDS    = ["linear", "power", "exponential", "gaussian", "poly2", "poly3"]


class AnalysisPage(QWidget):
    """数据分析页 — 通过共享项目树选择分析数据。"""

    # 由 main_window 框架路由的节点类型
    tree_filter_kinds: List[str] = [
        "folder", "data_file", "image_work", "series", "curve",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: Optional[Dict[str, Any]] = None
        # 已选分析数据列表：List[{"kind": str, "node_id": str, "label": str}]
        self._selected_inputs: List[dict] = []
        self._setup_ui()

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
        splitter.addWidget(self._build_right())
        splitter.setSizes([320, 660])

    def _build_left(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(260)
        panel.setMaximumWidth(380)
        lv = QVBoxLayout(panel)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(6)

        lv.addWidget(make_section_label("分析类型"))
        self._type_combo = ComboBox(self)
        self._type_combo.addItems(_TYPE_LABELS)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        lv.addWidget(self._type_combo)

        lv.addWidget(make_hsep())
        lv.addWidget(make_section_label("已选分析数据（从项目树中双击添加）"))

        self._input_list = ListWidget(self)
        self._input_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        lv.addWidget(self._input_list)

        clear_row = QHBoxLayout()
        btn_clear = PushButton(FIF.DELETE, "清除", self)
        btn_clear.setFixedHeight(28)
        btn_clear.clicked.connect(self._clear_inputs)
        clear_row.addWidget(btn_clear)
        btn_remove = PushButton(FIF.REMOVE, "移除选中", self)
        btn_remove.setFixedHeight(28)
        btn_remove.clicked.connect(self._remove_selected_inputs)
        clear_row.addWidget(btn_remove)
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
        self._peak_dist_label = BodyLabel("最小间距（采样点数）:")
        self._peak_dist_edit = LineEdit(self)
        self._peak_dist_edit.setText("1")
        self._peak_prom_label = BodyLabel("最小突出度（留空不限）:")
        self._peak_prom_edit = LineEdit(self)
        self._peak_prom_edit.setPlaceholderText("不限")
        lv.addWidget(self._peak_height_label)
        lv.addWidget(self._peak_height_edit)
        lv.addWidget(self._peak_dist_label)
        lv.addWidget(self._peak_dist_edit)
        lv.addWidget(self._peak_prom_label)
        lv.addWidget(self._peak_prom_edit)

        self._corr_method_label = BodyLabel("相关系数类型:")
        self._corr_method_combo = ComboBox(self)
        self._corr_method_combo.addItems(["Pearson", "Spearman"])
        lv.addWidget(self._corr_method_label)
        lv.addWidget(self._corr_method_combo)

        lv.addStretch()
        lv.addWidget(make_hsep())

        run_btn = PrimaryPushButton(FIF.PLAY, "运行分析")
        run_btn.clicked.connect(self._run_analysis)
        lv.addWidget(run_btn)

        save_btn = PushButton(FIF.SAVE, "保存结果")
        save_btn.clicked.connect(self._save_result)
        lv.addWidget(save_btn)

        report_btn = PushButton(FIF.DOCUMENT, "生成报告")
        report_btn.clicked.connect(self._on_generate_report)
        lv.addWidget(report_btn)

        self._on_type_changed(0)
        return panel

    def _build_right(self) -> QWidget:
        panel = QWidget()
        rv = QVBoxLayout(panel)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(6)
        rv.addWidget(make_section_label("分析结果"))

        if _HAS_MPL:
            self._figure = Figure(figsize=(6, 4), tight_layout=True)
            self._canvas = FigureCanvas(self._figure)
            self._canvas.setMinimumHeight(300)
            rv.addWidget(self._canvas, stretch=2)
        else:
            self._figure = None
            self._canvas = None
            rv.addWidget(BodyLabel("需要 matplotlib"), stretch=2)

        rv.addWidget(make_hsep())
        rv.addWidget(make_section_label("摘要"))
        self._summary_label = BodyLabel("（运行分析后显示结果）")
        self._summary_label.setWordWrap(True)
        self._summary_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        rv.addWidget(self._summary_label, stretch=1)
        return panel

    # ─────────────────────────────────────────────────────────
    # 共享树接口
    # ─────────────────────────────────────────────────────────

    def on_tree_node_selected(self, kind: str, node_id: str) -> None:
        """单击选中节点（只更新高亮，不加入分析列表）。"""
        pass

    def on_tree_node_activated(self, kind: str, node_id: str) -> None:
        """双击树节点 → 加入分析输入列表。"""
        if kind.endswith("_to_analysis"):
            kind = kind[:-12]
        if kind not in ("series", "curve", "data_file", "image_work"):
            return
        # 获取节点 label
        label = self._get_node_label(kind, node_id)
        # 去重
        if any(inp["node_id"] == node_id for inp in self._selected_inputs):
            return
        self._selected_inputs.append({"kind": kind, "node_id": node_id, "label": label})
        item = QListWidgetItem(label)
        item.setData(Qt.UserRole, {"kind": kind, "node_id": node_id})
        self._input_list.addItem(item)

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
        self._input_list.clear()

    def _remove_selected_inputs(self):
        to_remove: Set[str] = set()
        for item in self._input_list.selectedItems():
            d = item.data(Qt.UserRole)
            if d:
                to_remove.add(d["node_id"])
        self._selected_inputs = [x for x in self._selected_inputs
                                  if x["node_id"] not in to_remove]
        for i in range(self._input_list.count() - 1, -1, -1):
            item = self._input_list.item(i)
            if item.data(Qt.UserRole) and item.data(Qt.UserRole)["node_id"] in to_remove:
                self._input_list.takeItem(i)

    # ─────────────────────────────────────────────────────────
    # 类型切换
    # ─────────────────────────────────────────────────────────

    def _on_type_changed(self, idx: int):
        t = _TYPE_IDS[idx] if idx < len(_TYPE_IDS) else "curve_fit"
        is_fit  = t == "curve_fit"
        is_peak = t == "peak_detect"
        is_corr = t == "correlation"
        for w in [self._fit_model_label, self._fit_model_combo]:
            w.setVisible(is_fit)
        for w in [self._peak_height_label, self._peak_height_edit,
                  self._peak_dist_label, self._peak_dist_edit,
                  self._peak_prom_label, self._peak_prom_edit]:
            w.setVisible(is_peak)
        for w in [self._corr_method_label, self._corr_method_combo]:
            w.setVisible(is_corr)

    # ─────────────────────────────────────────────────────────
    # 获取分析数据
    # ─────────────────────────────────────────────────────────

    def _get_selected_data(self) -> List[tuple]:
        """返回 (xs, ys, name) 列表。"""
        result = []
        for inp in self._selected_inputs:
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
        t = _TYPE_IDS[self._type_combo.currentIndex()]
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
            self._show_result(t, selected)
        except Exception as e:
            InfoBar.error("分析失败", str(e), parent=self, position=InfoBarPosition.TOP)
            self._summary_label.setText(f"错误: {e}")

    def _do_fit(self, src: tuple) -> dict:
        from core.analysis_engine import fit_curve
        xs, ys, name = src
        model = _FIT_MODEL_IDS[self._fit_model_combo.currentIndex()]
        r = fit_curve(xs, ys, model)
        r["source_name"] = name
        r["analysis_type"] = "curve_fit"
        return r

    def _do_peaks(self, src: tuple) -> dict:
        from core.analysis_engine import detect_peaks
        xs, ys, name = src
        def _f(e, default):
            try: return float(e.text())
            except: return default
        def _i(e, default):
            try: return max(1, int(e.text()))
            except: return default
        r = detect_peaks(xs, ys,
                         min_height=_f(self._peak_height_edit, None),
                         min_distance=_i(self._peak_dist_edit, 1),
                         prominence=_f(self._peak_prom_edit, None))
        r["source_name"] = name
        r["analysis_type"] = "peak_detect"
        return r

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

    # ─────────────────────────────────────────────────────────
    # 结果显示
    # ─────────────────────────────────────────────────────────

    def _show_result(self, t: str, selected: list):
        r = self._result
        if r is None:
            return
        self._draw_result(t, selected, r)
        self._write_summary(t, r)

    def _draw_result(self, t: str, selected: list, r: dict):
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
                           marker="^", label=f"峰值 ({len(peaks)}个)")
            ax.legend(facecolor=bg, edgecolor=fg, labelcolor=fg, fontsize=8)

        elif t == "correlation" and len(selected) >= 2:
            _, ys1, n1 = selected[0]
            _, ys2, n2 = selected[1]
            nn = min(len(ys1), len(ys2))
            ax.scatter(ys1[:nn], ys2[:nn], s=15, color="#0078D4", alpha=0.7)
            ax.set_xlabel(n1, color=fg)
            ax.set_ylabel(n2, color=fg)
            ax.set_title(f"r = {r.get('r', 0):.4f}", color=fg)

        elif t == "statistics" and selected:
            xs, ys, name = selected[0]
            ax.plot(xs, ys, color="#0078D4", linewidth=1.4, label=name)
            mean = r.get("y_mean", 0)
            ax.axhline(mean, color="#D13438", linestyle="--", linewidth=1,
                       label=f"均值={mean:.4g}")
            ax.legend(facecolor=bg, edgecolor=fg, labelcolor=fg, fontsize=8)

        self._canvas.draw()

    def _write_summary(self, t: str, r: dict):
        if t == "curve_fit":
            params = r.get("params", [])
            names = r.get("param_names", [])
            param_str = "  ".join(f"{n}={v:.4g}" for n, v in zip(names, params))
            text = (f"模型: {r.get('model', '')}\n"
                    f"方程: {r.get('equation', '')}\n"
                    f"参数: {param_str}\n"
                    f"R² = {r.get('r2', float('nan')):.6f}")
        elif t == "peak_detect":
            peaks = r.get("peaks", [])
            n = r.get("count", 0)
            peak_str = "\n".join(f"  峰{i+1}: x={p['x']:.4g}  y={p['y']:.4g}"
                                 for i, p in enumerate(peaks[:10]))
            extra = "\n  （仅显示前10个）" if n > 10 else ""
            text = f"共检测到 {n} 个峰值\n{peak_str}{extra}"
        elif t == "statistics":
            text = (f"N = {r.get('n', 0)}\n"
                    f"X: 均值={r.get('x_mean', 0):.4g}  σ={r.get('x_std', 0):.4g}"
                    f"  范围=[{r.get('x_min', 0):.4g}, {r.get('x_max', 0):.4g}]\n"
                    f"Y: 均值={r.get('y_mean', 0):.4g}  σ={r.get('y_std', 0):.4g}"
                    f"  范围=[{r.get('y_min', 0):.4g}, {r.get('y_max', 0):.4g}]\n"
                    f"Y 中位数={r.get('y_median', 0):.4g}"
                    f"  Q1={r.get('y_p25', 0):.4g}  Q3={r.get('y_p75', 0):.4g}")
        elif t == "correlation":
            p = r.get("p_value")
            p_str = f"  p={p:.4g}" if p is not None else ""
            text = (f"方法: {r.get('method', '')}\n"
                    f"相关系数 r = {r.get('r', 0):.6f}{p_str}\n"
                    f"数据: {r.get('name1', '')} vs {r.get('name2', '')}")
        else:
            text = str(r)
        self._summary_label.setText(text)

    # ─────────────────────────────────────────────────────────
    # 保存分析结果
    # ─────────────────────────────────────────────────────────

    def _save_result(self):
        if self._result is None:
            InfoBar.warning("提示", "请先运行分析", parent=self,
                            position=InfoBarPosition.TOP)
            return
        p = project_manager.current_project
        if p is None:
            return
        from models.schemas import AnalysisResult, DataSeries
        t = self._result.get("analysis_type", "analysis")
        ar = AnalysisResult(
            name=f"{_TYPE_LABELS[self._type_combo.currentIndex()]}结果",
            analysis_type=t,
            summary={k: v for k, v in self._result.items()
                     if k not in ("fit_x", "fit_y", "peaks")},
        )
        if t == "curve_fit" and "fit_x" in self._result:
            s = DataSeries(
                name=f"fit_{self._result.get('model', 'curve')}",
                x=self._result["fit_x"],
                y=self._result["fit_y"],
                source="computed",
            )
            if not p.datasets:
                project_manager.add_dataset("分析结果")
            project_manager.add_series_to_dataset(p.datasets[-1].id, s)
            ar.result_series_id = s.id
        project_manager.add_analysis(ar)
        InfoBar.success("已保存", "分析结果已保存至项目", parent=self,
                        position=InfoBarPosition.TOP)

    # ─────────────────────────────────────────────────────────
    # 报告模板
    # ─────────────────────────────────────────────────────────

    def _on_generate_report(self):
        from ui.dialogs.report_template_dialog import ReportTemplateDialog
        dlg = ReportTemplateDialog(self, self._result)
        dlg.exec()

    # ─────────────────────────────────────────────────────────
    # 外部接口
    # ─────────────────────────────────────────────────────────

    def update_theme(self):
        if self._result:
            self._draw_result(
                self._result.get("analysis_type", ""),
                self._get_selected_data(),
                self._result,
            )
