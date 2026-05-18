from __future__ import annotations

from matplotlib.patches import Circle, Rectangle

from core.extension_api import ExtensionConfigField, PlotExtension
from core.value_parsing import coerce_float
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION


def _coord_mode(axis, params):
    return axis.transData if str(params.get("coordinate_mode", "axes_fraction")).strip().lower() == "data" else axis.transAxes


def _draw_text(axis, transform, params):
    x_value = coerce_float(params.get("x", 0.08), 0.08) or 0.08
    y_value = coerce_float(params.get("y", 0.9), 0.9) or 0.9
    color = str(params.get("color", "#222222") or "#222222")
    text = str(params.get("text", "请在这里补充说明") or "请在这里补充说明")
    axis.text(
        x_value,
        y_value,
        text,
        transform=transform,
        color=color,
        fontsize=max(6, int(coerce_float(params.get("font_size", 11), 11) or 11)),
        alpha=min(1.0, max(0.0, coerce_float(params.get("alpha", 0.95), 0.95) or 0.95)),
        rotation=coerce_float(params.get("rotation", 0.0), 0.0) or 0.0,
        ha=str(params.get("horizontal_align", "left") or "left"),
        va=str(params.get("vertical_align", "center") or "center"),
        bbox={"boxstyle": "round,pad=0.25", "fc": "#ffffff", "ec": color, "alpha": 0.82} if bool(params.get("show_box", True)) else None,
    )


def _draw_arrow(axis, coord_system, params):
    start_x = coerce_float(params.get("start_x", 0.18), 0.18) or 0.18
    start_y = coerce_float(params.get("start_y", 0.82), 0.82) or 0.82
    end_x = coerce_float(params.get("end_x", 0.72), 0.72) or 0.72
    end_y = coerce_float(params.get("end_y", 0.24), 0.24) or 0.24
    color = str(params.get("color", "#D13438") or "#D13438")
    text = str(params.get("text", "关键趋势") or "关键趋势")
    axis.annotate(
        text,
        xy=(end_x, end_y),
        xytext=(start_x, start_y),
        xycoords=coord_system,
        textcoords=coord_system,
        color=str(params.get("text_color", color) or color),
        fontsize=max(6, int(coerce_float(params.get("font_size", 11), 11) or 11)),
        bbox={"boxstyle": "round,pad=0.25", "fc": "#ffffff", "ec": color, "alpha": 0.85} if text else None,
        arrowprops={
            "arrowstyle": str(params.get("arrow_style", "->") or "->"),
            "color": color,
            "linewidth": max(0.1, coerce_float(params.get("line_width", 1.8), 1.8) or 1.8),
            "alpha": min(1.0, max(0.0, coerce_float(params.get("alpha", 0.95), 0.95) or 0.95)),
        },
    )


def _draw_rectangle(axis, transform, params):
    patch = Rectangle(
        (
            coerce_float(params.get("x", 0.14), 0.14) or 0.14,
            coerce_float(params.get("y", 0.2), 0.2) or 0.2,
        ),
        max(0.0, coerce_float(params.get("width", 0.28), 0.28) or 0.28),
        max(0.0, coerce_float(params.get("height", 0.18), 0.18) or 0.18),
        transform=transform,
        facecolor=str(params.get("face_color", "#f7d8d8") or "#f7d8d8") if bool(params.get("fill", False)) else "none",
        edgecolor=str(params.get("edge_color", "#c23934") or "#c23934"),
        linewidth=max(0.1, coerce_float(params.get("line_width", 1.6), 1.6) or 1.6),
        linestyle=str(params.get("line_style", "--") or "--"),
        alpha=min(1.0, max(0.0, coerce_float(params.get("alpha", 0.22), 0.22) or 0.22)),
        fill=bool(params.get("fill", False)),
        clip_on=False,
    )
    axis.add_patch(patch)


def _draw_circle(axis, transform, params):
    patch = Circle(
        (
            coerce_float(params.get("x", 0.5), 0.5) or 0.5,
            coerce_float(params.get("y", 0.5), 0.5) or 0.5,
        ),
        max(0.0, coerce_float(params.get("radius", 0.12), 0.12) or 0.12),
        transform=transform,
        facecolor=str(params.get("face_color", "#ffd966") or "#ffd966") if bool(params.get("fill", False)) else "none",
        edgecolor=str(params.get("edge_color", "#ff8c00") or "#ff8c00"),
        linewidth=max(0.1, coerce_float(params.get("line_width", 1.6), 1.6) or 1.6),
        linestyle=str(params.get("line_style", "--") or "--"),
        alpha=min(1.0, max(0.0, coerce_float(params.get("alpha", 0.22), 0.22) or 0.22)),
        fill=bool(params.get("fill", False)),
        clip_on=False,
    )
    axis.add_patch(patch)


def draw_annotation(plot_context, params):
    axis = plot_context.axis
    if axis is None:
        return
    mode = str(params.get("mode", "text") or "text").strip().lower()
    transform = _coord_mode(axis, params)
    coord_system = "data" if transform is axis.transData else "axes fraction"
    if mode == "arrow":
        _draw_arrow(axis, coord_system, params)
        return
    if mode == "rectangle":
        _draw_rectangle(axis, transform, params)
        return
    if mode == "circle":
        _draw_circle(axis, transform, params)
        return
    _draw_text(axis, transform, params)


def register_extensions(registry):
    registry.register_plot(
        PlotExtension(
            type="plot_annotation",
            name="统一标注",
            handler=draw_annotation,
            description="统一提供文字、箭头、矩形框和圆形框标注。",
            version=BUILTIN_EXTENSION_VERSION,
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            phases=("after_plot",),
            config_fields=[
                ExtensionConfigField(key="mode", label="标注模式", field_type="selective", default="text", choices=("text", "arrow", "rectangle", "circle")),
                ExtensionConfigField(key="coordinate_mode", label="坐标模式", field_type="selective", default="axes_fraction", choices=("axes_fraction", "data")),
                ExtensionConfigField(key="x", label="位置 X", field_type="number", default=0.08),
                ExtensionConfigField(key="y", label="位置 Y", field_type="number", default=0.9),
                ExtensionConfigField(key="text", label="文本", field_type="string", default="请在这里补充说明"),
                ExtensionConfigField(key="color", label="主颜色", field_type="color", default="#D13438"),
                ExtensionConfigField(key="text_color", label="文字颜色", field_type="color", default="#D13438"),
                ExtensionConfigField(key="font_size", label="字号", field_type="integer", default=11),
                ExtensionConfigField(key="alpha", label="透明度", field_type="limited", default=0.95, min_value=0.0, max_value=1.0, step=0.01),
                ExtensionConfigField(key="show_box", label="文本背景框", field_type="boolean", default=True),
                ExtensionConfigField(key="rotation", label="文字旋转", field_type="number", default=0.0),
                ExtensionConfigField(key="horizontal_align", label="水平对齐", field_type="selective", default="left", choices=("left", "center", "right")),
                ExtensionConfigField(key="vertical_align", label="垂直对齐", field_type="selective", default="center", choices=("top", "center", "bottom", "baseline")),
                ExtensionConfigField(key="start_x", label="箭头起点 X", field_type="number", default=0.18),
                ExtensionConfigField(key="start_y", label="箭头起点 Y", field_type="number", default=0.82),
                ExtensionConfigField(key="end_x", label="箭头终点 X", field_type="number", default=0.72),
                ExtensionConfigField(key="end_y", label="箭头终点 Y", field_type="number", default=0.24),
                ExtensionConfigField(key="arrow_style", label="箭头样式", field_type="selective", default="->", choices=("->", "-|>", "<->", "<|-|>")),
                ExtensionConfigField(key="line_width", label="线宽", field_type="number", default=1.6),
                ExtensionConfigField(key="line_style", label="线型", field_type="selective", default="--", choices=("-", "--", "-.", ":")),
                ExtensionConfigField(key="width", label="矩形宽度", field_type="number", default=0.28),
                ExtensionConfigField(key="height", label="矩形高度", field_type="number", default=0.18),
                ExtensionConfigField(key="radius", label="圆半径", field_type="number", default=0.12),
                ExtensionConfigField(key="fill", label="填充", field_type="boolean", default=False),
                ExtensionConfigField(key="edge_color", label="边框颜色", field_type="color", default="#c23934"),
                ExtensionConfigField(key="face_color", label="填充颜色", field_type="color", default="#ffd966"),
            ],
        )
    )
