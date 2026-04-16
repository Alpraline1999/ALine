"""图表页面 — 共享项目树驱动的可视化"""

from __future__ import annotations

import json
import os
import platform
import re
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QListWidgetItem,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    CheckBox,
    ComboBox,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    ListWidget,
    PushButton,
    ToolButton,
    isDarkTheme,
)

from ui.theme import make_hsep, make_section_label

try:
    import matplotlib
    matplotlib.use("QtAgg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    from matplotlib import font_manager

    _sys = platform.system().lower()
    if _sys == "windows":
        _CJK_FONT_FILES = [
            r"C:\\Windows\\Fonts\\msyh.ttc",
            r"C:\\Windows\\Fonts\\msyhbd.ttc",
            r"C:\\Windows\\Fonts\\simhei.ttf",
            r"C:\\Windows\\Fonts\\simsun.ttc",
        ]
        _CJK_NAMES = ["Microsoft YaHei", "SimHei", "SimSun", "Arial Unicode MS"]
    else:
        _CJK_FONT_FILES = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        ]
        _CJK_NAMES = ["Noto Sans CJK JP", "Noto Sans CJK SC", "WenQuanYi Micro Hei", "SimHei"]

    _selected_font = None
    for _f in _CJK_FONT_FILES:
        if not os.path.exists(_f):
            continue
        try:
            font_manager.fontManager.addfont(_f)
            _prop = font_manager.FontProperties(fname=_f)
            _name = _prop.get_name()
            if _name:
                _selected_font = _name
                break
        except Exception:
            continue

    if _selected_font is None:
        _available_names = {fm.name for fm in font_manager.fontManager.ttflist if fm.name}
        _selected_font = next((n for n in _CJK_NAMES if n in _available_names), None)

    if _selected_font:
        matplotlib.rcParams["font.family"] = [_selected_font, "sans-serif"]
    else:
        matplotlib.rcParams["font.family"] = ["sans-serif"]
    matplotlib.rcParams["font.sans-serif"] = [
        "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "WenQuanYi Micro Hei", "DejaVu Sans"
    ]
    matplotlib.rcParams["font.size"] = max(1, float(matplotlib.rcParams.get("font.size", 10) or 10))
    matplotlib.rcParams["axes.unicode_minus"] = False
    HAS_MATPLOTLIB = True
    _MATPLOTLIB_ERROR = ""
except Exception as _e:
    HAS_MATPLOTLIB = False
    _MATPLOTLIB_ERROR = f"{type(_e).__name__}: {_e}"

from core.project_manager import project_manager

_STYLES = [
    ("实线 —",         "-",   ""),
    ("虚线 - -",       "--",  ""),
    ("点线 ···",       ":",   ""),
    ("点划线 —·",      "-.",  ""),
    ("散点 ○",         "",    "o"),
    ("散点 □",         "",    "s"),
    ("散点 △",         "",    "^"),
    ("散点+线 ○—",     "-",   "o"),
    ("散点+线 □—",     "-",   "s"),
]
_STYLE_LABELS     = [s[0] for s in _STYLES]
_STYLE_LINESTYLES = [s[1] for s in _STYLES]
_STYLE_MARKERS    = [s[2] for s in _STYLES]


class ChartPage(QWidget):
    """数据可视化页面 — 由共享项目树驱动，不再含内置曲线列表。"""

    # 对外信号：通知 main_window 刷新树（当保存模板时）
    project_modified = Signal()

    # 页面可显示的节点类型（main_window 按此过滤共享树）
    tree_filter_kinds: List[str] = [
        "folder", "data_file", "image_work", "figure_template",
        "series", "curve",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        # 当前图表中的数据系列列表
        # 每项: {"name": str, "x": list, "y": list, "y_err": list|None,
        #        "color": str, "obj_id": str, "source": str}
        self._chart_series: List[dict] = []
        self._curve_styles: Dict[str, dict] = {}  # name → {color, linestyle, marker}
        self._style_target: Optional[str] = None

        self._redraw_timer = QTimer(self)
        self._redraw_timer.setSingleShot(True)
        self._redraw_timer.setInterval(300)
        self._redraw_timer.timeout.connect(self._redraw_now)

        self._setup_ui()

    # ──────────────────────────── UI ────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setHandleWidth(6)

        # ── 左侧控制面板 ──────────────────────────────────────────────
        left_card = CardWidget(self)
        lv = QVBoxLayout(left_card)
        lv.setContentsMargins(12, 12, 12, 12)
        lv.setSpacing(8)

        lv.addWidget(make_section_label("已绘图曲线", left_card))

        # 当前图表中的系列（可多选+删除）
        self._chart_list = ListWidget(left_card)
        self._chart_list.setSelectionMode(ListWidget.MultiSelection)
        self._chart_list.currentItemChanged.connect(self._on_current_changed)
        lv.addWidget(self._chart_list)

        sel_row = QHBoxLayout()
        self._btn_clear = PushButton(FIF.DELETE, "清除绘图", left_card)
        self._btn_clear.setFixedHeight(30)
        self._btn_clear.clicked.connect(self._on_clear_chart)
        sel_row.addWidget(self._btn_clear)
        self._btn_remove = PushButton(FIF.REMOVE, "移除选中", left_card)
        self._btn_remove.setFixedHeight(30)
        self._btn_remove.clicked.connect(self._on_remove_selected)
        sel_row.addWidget(self._btn_remove)
        lv.addLayout(sel_row)

        lv.addWidget(make_hsep(left_card))

        # 曲线样式
        lv.addWidget(make_section_label("曲线样式(选中后设置)", left_card))
        self._style_target_label = BodyLabel("— 未选中 —", left_card)
        self._style_target_label.setStyleSheet("color: gray; font-size: 11px;")
        self._style_target_label.setWordWrap(True)
        lv.addWidget(self._style_target_label)

        style_row = QHBoxLayout()
        style_row.setSpacing(6)
        style_row.addWidget(BodyLabel("颜色:", left_card))
        self._style_color_btn = PushButton(left_card)
        self._style_color_btn.setFixedSize(28, 28)
        self._style_color_btn.setEnabled(False)
        self._style_color_btn.clicked.connect(self._on_style_color_click)
        style_row.addWidget(self._style_color_btn)
        self._style_reset_color_btn = ToolButton(FIF.CANCEL, left_card)
        self._style_reset_color_btn.setFixedSize(24, 24)
        self._style_reset_color_btn.setEnabled(False)
        self._style_reset_color_btn.clicked.connect(self._on_style_reset_color)
        style_row.addWidget(self._style_reset_color_btn)
        style_row.addWidget(BodyLabel("线型:", left_card))
        self._style_line_combo = ComboBox(left_card)
        self._style_line_combo.addItems(_STYLE_LABELS)
        self._style_line_combo.setEnabled(False)
        self._style_line_combo.currentIndexChanged.connect(self._on_style_line_changed)
        style_row.addWidget(self._style_line_combo, 1)
        lv.addLayout(style_row)

        lv.addWidget(make_hsep(left_card))

        # 简单坐标轴控制（快速使用；完整设置在高级对话框中）
        lv.addWidget(make_section_label("坐标轴标签", left_card))
        xlabel_row = QHBoxLayout()
        xlabel_row.addWidget(BodyLabel("X:", left_card))
        self._x_label_edit = LineEdit(left_card)
        self._x_label_edit.setPlaceholderText("X")
        self._x_label_edit.textChanged.connect(self._redraw)
        xlabel_row.addWidget(self._x_label_edit)
        lv.addLayout(xlabel_row)

        ylabel_row = QHBoxLayout()
        ylabel_row.addWidget(BodyLabel("Y:", left_card))
        self._y_label_edit = LineEdit(left_card)
        self._y_label_edit.setPlaceholderText("Y")
        self._y_label_edit.textChanged.connect(self._redraw)
        ylabel_row.addWidget(self._y_label_edit)
        lv.addLayout(ylabel_row)

        lv.addWidget(make_hsep(left_card))

        # 图表主题 + 误差棒
        lv.addWidget(make_section_label("图表主题", left_card))
        theme_row = QHBoxLayout()
        theme_row.addWidget(BodyLabel("主题:", left_card))
        self._theme_combo = ComboBox(left_card)
        self._theme_combo.addItems(["默认", "Nature", "IEEE", "ACS", "简洁黑白"])
        self._theme_combo.currentIndexChanged.connect(self._redraw_now)
        theme_row.addWidget(self._theme_combo, 1)
        lv.addLayout(theme_row)

        self._errbar_cb = CheckBox("显示误差棒", left_card)
        self._errbar_cb.stateChanged.connect(self._redraw_now)
        lv.addWidget(self._errbar_cb)

        lv.addWidget(make_hsep(left_card))

        # 操作按钮行
        btn_grid = QGridLayout()
        btn_grid.setSpacing(4)
        self._btn_advanced = PushButton(FIF.SETTING, "高级设置", left_card)
        self._btn_advanced.setFixedHeight(32)
        self._btn_advanced.clicked.connect(self._on_advanced_settings)
        btn_grid.addWidget(self._btn_advanced, 0, 0)

        self._btn_save_template = PushButton(FIF.SAVE, "保存模板", left_card)
        self._btn_save_template.setFixedHeight(32)
        self._btn_save_template.clicked.connect(self._on_save_template)
        btn_grid.addWidget(self._btn_save_template, 0, 1)

        self._btn_export = PushButton(FIF.SHARE, "导出图片", left_card)
        self._btn_export.setFixedHeight(32)
        self._btn_export.clicked.connect(self._on_export_image)
        btn_grid.addWidget(self._btn_export, 1, 0, 1, 2)

        btn_grid.setColumnStretch(0, 1)
        btn_grid.setColumnStretch(1, 1)
        lv.addLayout(btn_grid)

        lv.addStretch()
        left_card.setMinimumWidth(220)
        left_card.setMaximumWidth(320)
        splitter.addWidget(left_card)

        # ── 右侧画布 ────────────────────────────────────────────────
        right_card = CardWidget(self)
        rv = QVBoxLayout(right_card)
        rv.setContentsMargins(8, 8, 8, 8)

        if HAS_MATPLOTLIB:
            self._figure = Figure()
            self._canvas = FigureCanvas(self._figure)
            self._canvas.setMinimumHeight(300)
            rv.addWidget(self._canvas)
        else:
            errtxt = (f"matplotlib 加载失败：{_MATPLOTLIB_ERROR}"
                      if _MATPLOTLIB_ERROR else
                      "请安装 matplotlib：uv pip install matplotlib")
            no_mpl = BodyLabel(errtxt, self)
            no_mpl.setAlignment(Qt.AlignCenter)
            no_mpl.setWordWrap(True)
            rv.addWidget(no_mpl)
            self._figure = None
            self._canvas = None

        splitter.addWidget(right_card)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

    # ──────────────────────────── 共享树接口 ─────────────────────────────

    def on_tree_node_selected(self, kind: str, node_id: str) -> None:
        """主窗口路由过来的选中事件 → 将节点下的系列加入图表。"""
        pass  # 单击不自动加入，双击（node_activated）才加入

    def on_tree_node_activated(self, kind: str, node_id: str) -> None:
        """双击树节点 → 将对应数据加入图表。"""
        # 规范化 kind（右键菜单会发 xxx_to_chart）
        if kind.endswith("_to_chart"):
            kind = kind[:-9]

        series_list = project_manager.get_all_series_from_node(kind, node_id)
        if not series_list:
            return
        for s in series_list:
            self.add_series_to_chart({
                "name": s.name,
                "x": list(s.x),
                "y": list(s.y),
                "y_err": list(s.y_err) if s.y_err else None,
                "color": s.color,
                "obj_id": s.id,
                "source": "tree",
            })

    def add_series_to_chart(self, series_data: dict) -> None:
        """将一条数据系列加入图表（去重 by obj_id）。"""
        obj_id = series_data.get("obj_id", "")
        # 去重
        if obj_id and any(c.get("obj_id") == obj_id for c in self._chart_series):
            return
        self._chart_series.append(series_data)
        self._refresh_chart_list()
        self._redraw_now()

    # ──────────────────────────── 模板支持 ──────────────────────────────

    def load_template(self, template_node_id: str) -> None:
        """从工具集加载绘图模板，恢复全部 FigureConfig 字段。"""
        p = project_manager.current_project
        if p is None or p.tree is None:
            return
        node = p.tree.get_node(template_node_id)
        if node is None or node.kind != "figure_template":
            return
        fig = p.find_figure(node.figure_id)
        if fig is None:
            return

        # 恢复主题
        themes = ["默认", "Nature", "IEEE", "ACS", "简洁黑白"]
        if fig.theme in themes:
            self._theme_combo.setCurrentIndex(themes.index(fig.theme))

        # 恢复轴标签（typed_axis_config 优先，回退 axis_config dict）
        ax = fig.typed_axis_config
        self._x_label_edit.setText(ax.x_label or "X")
        self._y_label_edit.setText(ax.y_label or "Y")

        # 恢复误差棒
        self._errbar_cb.setChecked(fig.show_errbar)

        self._redraw_now()

    def _on_save_template(self) -> None:
        """将当前绘图配置保存为 FigureConfig 挂到工具集树。"""
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "保存绘图模板", "模板名称:")
        if not ok or not name.strip():
            return

        from models.schemas import FigureConfig, AxisConfig
        themes = ["默认", "Nature", "IEEE", "ACS", "简洁黑白"]
        theme_name = self._theme_combo.currentText()

        ax = AxisConfig(
            x_label=self._x_label_edit.text().strip() or "X",
            y_label=self._y_label_edit.text().strip() or "Y",
        )
        config = FigureConfig(
            name=name.strip(),
            theme=theme_name,
            show_errbar=self._errbar_cb.isChecked(),
            typed_axis_config=ax,
        )
        node = project_manager.add_figure_template(config)
        if node:
            InfoBar.success(
                title="已保存", content=f"模板「{name}」已存入工具集",
                position=InfoBarPosition.TOP, duration=2500, parent=self,
            )
            self.project_modified.emit()

    # ──────────────────────────── 高级设置 ──────────────────────────────

    def _on_advanced_settings(self) -> None:
        from ui.dialogs.advanced_figure_dialog import AdvancedFigureDialog
        dlg = AdvancedFigureDialog(self, self._get_current_config())
        if dlg.exec():
            cfg = dlg.get_config()
            self._apply_advanced_config(cfg)
            self._redraw_now()

    def _get_current_config(self) -> dict:
        themes = ["默认", "Nature", "IEEE", "ACS", "简洁黑白"]
        return {
            "theme": self._theme_combo.currentText(),
            "x_label": self._x_label_edit.text(),
            "y_label": self._y_label_edit.text(),
            "show_errbar": self._errbar_cb.isChecked(),
            "x_min": "",
            "x_max": "",
            "y_min": "",
            "y_max": "",
            "x_log": False,
            "y_log": False,
            "grid": True,
            "legend_pos": "best",
            "font_size": 10,
        }

    def _apply_advanced_config(self, cfg: dict) -> None:
        themes = ["默认", "Nature", "IEEE", "ACS", "简洁黑白"]
        if cfg.get("theme") in themes:
            self._theme_combo.setCurrentIndex(themes.index(cfg["theme"]))
        self._x_label_edit.setText(cfg.get("x_label", "X"))
        self._y_label_edit.setText(cfg.get("y_label", "Y"))
        self._errbar_cb.setChecked(cfg.get("show_errbar", False))
        # 存储高级设置供 _redraw_now 读取
        self._adv_cfg = cfg

    # ──────────────────────────── 内部状态管理 ────────────────────────────

    def _refresh_chart_list(self) -> None:
        prev_names = {
            item.data(Qt.UserRole).get("name")
            for item in self._chart_list.selectedItems()
        }
        self._chart_list.clear()
        for c in self._chart_series:
            item = QListWidgetItem(c["name"])
            item.setData(Qt.UserRole, c)
            if c["name"] in prev_names:
                item.setSelected(True)
            self._chart_list.addItem(item)

    def _on_clear_chart(self) -> None:
        self._chart_series.clear()
        self._curve_styles.clear()
        self._refresh_chart_list()
        self._redraw_now()

    def _on_remove_selected(self) -> None:
        to_remove = {
            item.data(Qt.UserRole).get("name")
            for item in self._chart_list.selectedItems()
        }
        self._chart_series = [c for c in self._chart_series if c["name"] not in to_remove]
        for k in list(self._curve_styles):
            if k in to_remove:
                del self._curve_styles[k]
        self._refresh_chart_list()
        self._redraw_now()

    def receive_data(self, data_type: str, obj_id: str):
        """来自数据管理页的快捷发送。"""
        series_list = project_manager.get_all_series_from_node(data_type, obj_id)
        for s in series_list:
            self.add_series_to_chart({
                "name": s.name,
                "x": list(s.x),
                "y": list(s.y),
                "y_err": list(s.y_err) if s.y_err else None,
                "color": s.color,
                "obj_id": s.id,
                "source": "send",
            })

    # ──────────────────────────── 绘图 ──────────────────────────────────

    _ACADEMIC_THEMES = {
        "Nature": {"font.size": 9, "axes.linewidth": 1.2, "xtick.major.width": 1.2,
                   "ytick.major.width": 1.2, "lines.linewidth": 1.5},
        "IEEE":   {"font.size": 8, "axes.linewidth": 1.0, "xtick.major.width": 1.0,
                   "ytick.major.width": 1.0, "lines.linewidth": 1.2, "font.family": "serif"},
        "ACS":    {"font.size": 9, "axes.linewidth": 1.5, "xtick.major.width": 1.5,
                   "ytick.major.width": 1.5, "lines.linewidth": 1.8},
        "简洁黑白": {"font.size": 10, "axes.linewidth": 1.2, "lines.linewidth": 1.5},
    }

    def _redraw(self):
        self._redraw_timer.start()

    def _redraw_now(self):
        if not HAS_MATPLOTLIB or self._figure is None:
            return
        self._figure.clear()
        ax = self._figure.add_subplot(111)

        dark = isDarkTheme()
        bg = "#1e1e1e" if dark else "#ffffff"
        fg = "#cccccc" if dark else "#222222"
        grid_c = "#444444" if dark else "#dddddd"

        self._figure.patch.set_facecolor(bg)
        ax.set_facecolor(bg)
        ax.tick_params(colors=fg, labelcolor=fg)
        ax.xaxis.label.set_color(fg)
        ax.yaxis.label.set_color(fg)
        ax.title.set_color(fg)
        for spine in ax.spines.values():
            spine.set_edgecolor(fg)

        adv = getattr(self, "_adv_cfg", {})
        grid_on = adv.get("grid", True)
        ax.grid(grid_on, color=grid_c, linestyle="--", linewidth=0.5, alpha=0.7)

        theme_name = self._theme_combo.currentText()
        if theme_name in self._ACADEMIC_THEMES:
            for k, v in self._ACADEMIC_THEMES[theme_name].items():
                plt.rcParams[k] = v

        fsize = adv.get("font_size", 10)
        if fsize:
            matplotlib.rcParams["font.size"] = max(1, fsize)

        show_errbar = self._errbar_cb.isChecked()
        bw_colors = ["#000000", "#444444", "#888888", "#aaaaaa"]
        bw_idx = 0
        _MAX_PTS = 2000

        selected_items = self._chart_list.selectedItems()
        visible_series = (
            [item.data(Qt.UserRole) for item in selected_items]
            if selected_items else self._chart_series
        )

        for c in visible_series:
            if c is None:
                continue
            name = c["name"]
            ov = self._curve_styles.get(name, {})
            color = ov.get("color") or c.get("color")
            ls = ov.get("linestyle", "-")
            marker = ov.get("marker", "")
            kw: dict = {"label": name, "linestyle": ls or "none"}
            if marker:
                kw["marker"] = marker
                kw["markersize"] = 5
            if theme_name == "简洁黑白":
                kw["color"] = bw_colors[bw_idx % len(bw_colors)]
                bw_idx += 1
            elif color:
                kw["color"] = color

            px, py = list(c.get("x", [])), list(c.get("y", []))
            n_pts = len(px)
            if n_pts > _MAX_PTS:
                stride = n_pts // _MAX_PTS
                px = px[::stride]
                py = py[::stride]
            y_err = c.get("y_err")
            if show_errbar and y_err and len(y_err) == len(c.get("x", [])):
                if n_pts > _MAX_PTS:
                    y_err = y_err[::stride]
                kw.pop("linestyle", None)
                ax.errorbar(px, py, yerr=y_err,
                            fmt=f"{marker or 'o'}{ls or '-'}",
                            linewidth=1.4, capsize=3,
                            **{k: v for k, v in kw.items() if k not in ("marker", "markersize")})
            else:
                ax.plot(px, py, linewidth=1.4, **kw)

        if visible_series:
            legend_pos = adv.get("legend_pos", "best")
            ax.legend(facecolor=bg, edgecolor=fg, labelcolor=fg, fontsize=8,
                      loc=legend_pos or "best")

        xl = self._x_label_edit.text().strip()
        yl = self._y_label_edit.text().strip()
        ax.set_xlabel(xl or "X")
        ax.set_ylabel(yl or "Y")

        x_min = _safe_float(adv.get("x_min"))
        x_max = _safe_float(adv.get("x_max"))
        y_min = _safe_float(adv.get("y_min"))
        y_max = _safe_float(adv.get("y_max"))
        if x_min is not None or x_max is not None:
            ax.set_xlim(left=x_min, right=x_max)
        if y_min is not None or y_max is not None:
            ax.set_ylim(bottom=y_min, top=y_max)

        if adv.get("x_log"):
            ax.set_xscale("log")
        if adv.get("y_log"):
            ax.set_yscale("log")

        self._figure.subplots_adjust(left=0.12, right=0.96, top=0.96, bottom=0.10)
        self._canvas.draw()

    # ──────────────────────────── 样式面板 ──────────────────────────────

    def _on_current_changed(self, current, _prev):
        if current is None:
            self._set_style_enabled(False)
        else:
            self._set_style_enabled(True, current.data(Qt.UserRole))

    def _set_style_enabled(self, enabled: bool, curve: Optional[dict] = None):
        self._style_color_btn.setEnabled(enabled)
        self._style_reset_color_btn.setEnabled(enabled)
        self._style_line_combo.setEnabled(enabled)
        if enabled and curve:
            name = curve["name"]
            self._style_target = name
            self._style_target_label.setText(name[:30] + ("…" if len(name) > 30 else ""))
            ov = self._curve_styles.get(name, {})
            eff_color = ov.get("color") or curve.get("color") or "#888888"
            self._update_color_btn(eff_color)
            ls = ov.get("linestyle", "-")
            mk = ov.get("marker", "")
            try:
                idx = next(i for i, (sl, sm) in enumerate(
                    zip(_STYLE_LINESTYLES, _STYLE_MARKERS)) if sl == ls and sm == mk)
            except StopIteration:
                idx = 0
            self._style_line_combo.blockSignals(True)
            self._style_line_combo.setCurrentIndex(idx)
            self._style_line_combo.blockSignals(False)
        else:
            self._style_target = None
            self._style_target_label.setText("— 未选中 —")
            self._update_color_btn("#888888")

    def _update_color_btn(self, color_str: str):
        c = QColor(color_str)
        if not c.isValid():
            color_str = "#888888"
        self._style_color_btn.setStyleSheet(
            f"QPushButton{{background:{color_str};border:1px solid #888;border-radius:4px;}}"
            f"QPushButton:hover{{border:2px solid #aaa;}}"
        )

    def _on_style_color_click(self):
        if not self._style_target:
            return
        cur_c = self._curve_styles.get(self._style_target, {}).get("color", "#0078D4")
        color = QColorDialog.getColor(QColor(cur_c), self, "选择曲线颜色")
        if color.isValid():
            self._curve_styles.setdefault(self._style_target, {})["color"] = color.name()
            self._update_color_btn(color.name())
            self._redraw_now()

    def _on_style_reset_color(self):
        if not self._style_target:
            return
        self._curve_styles.get(self._style_target, {}).pop("color", None)
        # find default color from _chart_series
        for c in self._chart_series:
            if c["name"] == self._style_target:
                self._update_color_btn(c.get("color") or "#888888")
                break
        self._redraw_now()

    def _on_style_line_changed(self, idx: int):
        if not self._style_target:
            return
        s = self._curve_styles.setdefault(self._style_target, {})
        s["linestyle"] = _STYLE_LINESTYLES[idx]
        s["marker"] = _STYLE_MARKERS[idx]
        self._redraw_now()

    # ──────────────────────────── 文件操作 ──────────────────────────────

    def _on_export_image(self):
        if not HAS_MATPLOTLIB or self._figure is None:
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出图片", "chart.png", "PNG (*.png);;SVG (*.svg);;PDF (*.pdf)",
        )
        if file_path:
            self._figure.savefig(file_path, dpi=150, bbox_inches="tight")
            InfoBar.success(
                title="导出成功", content=file_path,
                position=InfoBarPosition.TOP, duration=3000, parent=self,
            )

    def update_theme(self):
        self._redraw_now()


# ─────────────────────── 工具函数 ────────────────────────

def _safe_float(v) -> Optional[float]:
    try:
        return float(str(v).strip()) if v not in (None, "", "None") else None
    except Exception:
        return None


def _load_data_file(file_path: str) -> List[dict]:
    """支持 CSV/TXT/DAT/TSV/JSON/NumPy .npy"""
    p = Path(file_path)
    name = p.stem
    suffix = p.suffix.lower()
    if suffix == ".npy":
        return _load_npy(p, name)
    if suffix == ".json":
        return _load_json(p, name)
    return _load_tabular(p, name)


def _load_npy(p: Path, name: str) -> List[dict]:
    arr = np.load(str(p))
    if arr.ndim == 1:
        return [{"name": name, "x": list(range(len(arr))), "y": arr.tolist(), "source": "import"}]
    if arr.ndim == 2:
        return _cols_to_curves(arr, name)
    raise ValueError("NumPy 数组维度应为 1 或 2")


def _load_json(p: Path, name: str) -> List[dict]:
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        if data and isinstance(data[0], (list, tuple)):
            return _cols_to_curves(np.array(data, dtype=float), name)
        if data and isinstance(data[0], dict):
            curves = []
            for i, item in enumerate(data):
                y = item.get("y", item.get("Y", []))
                x = item.get("x", item.get("X", list(range(len(y)))))
                n = item.get("name", f"{name}_{i + 1}")
                curves.append({"name": n, "x": list(map(float, x)), "y": list(map(float, y)), "source": "import"})
            return curves
    if isinstance(data, dict):
        y = data.get("y", data.get("Y", []))
        x = data.get("x", data.get("X", list(range(len(y)))))
        n = data.get("name", name)
        return [{"name": n, "x": list(map(float, x)), "y": list(map(float, y)), "source": "import"}]
    raise ValueError("无法识别的 JSON 结构")


def _load_tabular(p: Path, name: str) -> List[dict]:
    raw_lines: List[str] = []
    for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            with open(p, encoding=enc, newline="") as f:
                raw_lines = f.readlines()
            break
        except UnicodeDecodeError:
            continue
    if not raw_lines:
        raise ValueError("文件读取失败或为空")
    data_lines = [l.rstrip("\r\n") for l in raw_lines
                  if l.strip() and not l.lstrip().startswith(("#", "%", "!", "/"))]
    if not data_lines:
        raise ValueError("文件中无有效数据行")
    delimiter = _detect_delimiter(data_lines)
    col_names = None
    start_row = 0
    first_parts = _split_line(data_lines[0], delimiter)
    if not _all_numeric(first_parts) and len(first_parts) >= 2:
        col_names = [pp.strip().strip('"\'') for pp in first_parts]
        start_row = 1
    rows: List[List[float]] = []
    for line in data_lines[start_row:]:
        parts = _split_line(line, delimiter)
        try:
            row = [float(v) for v in parts if v.strip()]
            if row:
                rows.append(row)
        except ValueError:
            continue
    if not rows:
        raise ValueError("文件中未找到数值数据")
    col_counts = [len(r) for r in rows]
    ncols = max(set(col_counts), key=col_counts.count)
    rows = [r for r in rows if len(r) == ncols]
    arr = np.array(rows, dtype=float)
    if col_names and len(col_names) != ncols:
        col_names = None
    return _cols_to_curves(arr, name, col_names=col_names)


def _cols_to_curves(arr: np.ndarray, name: str, col_names=None) -> List[dict]:
    if arr.ndim == 1:
        return [{"name": name, "x": list(range(len(arr))), "y": arr.tolist(), "source": "import"}]
    n_cols = arr.shape[1]
    if n_cols < 2:
        return [{"name": name, "x": list(range(len(arr))), "y": arr[:, 0].tolist(), "source": "import"}]
    x = arr[:, 0].tolist()
    curves = []
    for i in range(1, n_cols):
        if col_names and len(col_names) > i:
            c_name = f"{name} / {col_names[i]}"
        else:
            c_name = name if n_cols == 2 else f"{name}_Y{i}"
        curves.append({"name": c_name, "x": x, "y": arr[:, i].tolist(), "source": "import"})
    return curves


def _detect_delimiter(lines: List[str]):
    sample = "\n".join(lines[:10])
    if "\t" in sample:
        return "\t"
    comma_count = sample.count(",")
    semi_count = sample.count(";")
    if comma_count > 0 or semi_count > 0:
        return "," if comma_count >= semi_count else ";"
    return None


def _split_line(line: str, delimiter) -> List[str]:
    if delimiter is None:
        return re.split(r"\s+", line.strip())
    return line.split(delimiter)


def _all_numeric(parts: List[str]) -> bool:
    for pp in parts:
        try:
            float(pp.strip())
        except (ValueError, AttributeError):
            return False
    return bool(parts)
