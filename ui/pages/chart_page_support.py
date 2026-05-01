from __future__ import annotations

import copy
from typing import Any, Dict, Optional

from core.extension_api import PlotExtension, PlotExtensionContext
from models.schemas import FigureState
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSizePolicy, QWidget
from qfluentwidgets import BodyLabel, FluentIcon as FIF, LineEdit, ToolButton
from ui.matplotlib_fonts import bootstrap_matplotlib_qtagg

_matplotlib, FigureCanvas, Figure, _MATPLOTLIB_ERROR = bootstrap_matplotlib_qtagg()
HAS_MATPLOTLIB = _matplotlib is not None


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
_ICON_PLOT_EXTENSION_HELP = getattr(FIF, "INFO", getattr(FIF, "HELP", FIF.SEARCH))
_PLOT_EXTENSION_TEACHING_TIP_TEXT = "左侧负责选择、配置并应用扩展；右侧展示当前扩展状态、参数说明，以及当前图表里已加载的扩展实例。"
_TICK_DIRECTION_CHOICES = ["默认", "out", "in", "inout"]
_LEGEND_ALPHA_DEFAULT = 0.8
_CANVAS_ALPHA_DEFAULT = 1.0
_GRID_ALPHA_DEFAULT = 0.7
_BASE_PLOT_STYLE_EXTRA_KEYS = {
    "tick_params",
    "legend_kwargs",
    "grid_kwargs",
    "line_defaults",
    "errorbar_kwargs",
    "axis_kwargs",
    "subplot_adjust",
    "spine_visibility",
    "spine_width",
    "figure_facecolor",
    "figure_facealpha",
    "axes_facecolor",
    "axes_facealpha",
}
_BASE_CURVE_STYLE_EXTENSION_TYPE = "base_curve_style_controls"
_BASE_PLOT_STYLE_EXTENSION_TYPE = "base_plot_style_controls"


def _apply_base_curve_style_patch(plot_context: PlotExtensionContext, options: Dict[str, Any]) -> None:
    if plot_context.phase != "before_plot":
        return
    patch = {
        key: copy.deepcopy(value)
        for key, value in dict(options or {}).items()
        if key in {"color", "linestyle", "marker", "linewidth", "marker_size", "alpha", "markevery", "dash_scale", "visible"}
    }
    if patch:
        plot_context.patch_selected_curve_style(patch)
        # 只 patch context，不直接操作 matplotlib 对象，确保后续曲线样式可覆盖


def _apply_base_plot_style_patch(plot_context: PlotExtensionContext, options: Dict[str, Any]) -> None:
    if plot_context.phase != "before_plot":
        return
    figure_fields = set(FigureState.model_fields.keys())
    figure_patch = {
        key: copy.deepcopy(value)
        for key, value in dict(options or {}).items()
        if key in figure_fields
    }
    if figure_patch:
        plot_context.patch_figure_state(figure_patch)
    style_patch = {
        key: copy.deepcopy(value)
        for key, value in dict(options or {}).items()
        if key in _BASE_PLOT_STYLE_EXTRA_KEYS
    }
    if style_patch:
        plot_context.patch_plot_style(style_patch)
        # 只 patch context，不直接操作 matplotlib 对象，确保后续绘图样式可覆盖


_BASE_CURVE_STYLE_EXTENSION = PlotExtension(
    type=_BASE_CURVE_STYLE_EXTENSION_TYPE,
    name="基础曲线样式",
    handler=_apply_base_curve_style_patch,
    source_kind="base",
    hidden=True,
)

_BASE_PLOT_STYLE_EXTENSION = PlotExtension(
    type=_BASE_PLOT_STYLE_EXTENSION_TYPE,
    name="基础绘图样式",
    handler=_apply_base_plot_style_patch,
    source_kind="base",
    hidden=True,
)


def set_compact_edit_width(edit: LineEdit, width: int = 96) -> None:
    edit.setMaximumWidth(width)


def connect_line_edit_commit(edit: LineEdit, slot) -> None:
    edit.editingFinished.connect(slot)


def alpha_slider_value(alpha: float) -> int:
    return int(round(max(0.0, min(1.0, alpha)) * 100.0))


def alpha_from_slider_value(value: int) -> float:
    return max(0.0, min(1.0, float(value) / 100.0))


def set_square_tool_button(button: ToolButton, size: int) -> None:
    button.setFixedSize(size, size)


def make_style_form_label(text: str, parent: Optional[QWidget] = None, *, minimum_width: int = 0) -> BodyLabel:
    label = BodyLabel(text, parent)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    label.setMinimumWidth(max(minimum_width, label.sizeHint().width()))
    label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
    return label
