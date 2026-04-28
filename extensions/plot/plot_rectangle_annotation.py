from matplotlib.patches import Rectangle

from core.extension_api import ExtensionConfigField, PlotExtension


def _as_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def draw_rectangle_annotation(plot_context, params):
    axis = plot_context.axis
    if axis is None:
        return

    transform = axis.transData if str(params.get("coordinate_mode", "axes_fraction")).strip().lower() == "data" else axis.transAxes
    x = _as_float(params.get("x", 0.14), 0.14)
    y = _as_float(params.get("y", 0.2), 0.2)
    width = max(0.0, _as_float(params.get("width", 0.28), 0.28))
    height = max(0.0, _as_float(params.get("height", 0.18), 0.18))
    alpha = min(1.0, max(0.0, _as_float(params.get("alpha", 0.22), 0.22)))
    fill = bool(params.get("fill", False))
    facecolor = str(params.get("face_color", "#f7d8d8")) if fill else "none"

    patch = Rectangle(
        (x, y),
        width,
        height,
        transform=transform,
        facecolor=facecolor,
        edgecolor=str(params.get("edge_color", "#c23934")),
        linewidth=max(0.1, _as_float(params.get("line_width", 1.6), 1.6)),
        linestyle=str(params.get("line_style", "--")),
        alpha=alpha,
        fill=fill,
        clip_on=False,
    )
    axis.add_patch(patch)


def register_extensions(registry):
    registry.register_plot(
        PlotExtension(
            type="plot_rectangle_annotation",
            name="矩形框",
            handler=draw_rectangle_annotation,
            description="在图中绘制矩形框，可用于圈选关注区域。",
            version="0.1.0",
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            phases=("after_plot",),
            config_fields=[
                ExtensionConfigField(key="coordinate_mode", description="坐标模式：axes_fraction 使用画布比例坐标，data 使用数据坐标。", field_type="selective", default="axes_fraction", choices=("axes_fraction", "data")),
                ExtensionConfigField(key="x", description="矩形左下角 X。", field_type="number", default=0.14),
                ExtensionConfigField(key="y", description="矩形左下角 Y。", field_type="number", default=0.2),
                ExtensionConfigField(key="width", description="矩形宽度。", field_type="number", default=0.28),
                ExtensionConfigField(key="height", description="矩形高度。", field_type="number", default=0.18),
                ExtensionConfigField(key="edge_color", description="边框颜色。", field_type="color", default="#c23934"),
                ExtensionConfigField(key="face_color", description="填充颜色。", field_type="color", default="#f7d8d8"),
                ExtensionConfigField(key="line_width", description="边框线宽。", field_type="number", default=1.6),
                ExtensionConfigField(key="line_style", description="边框线型。", field_type="selective", default="--", choices=("-", "--", "-.", ":")),
                ExtensionConfigField(key="alpha", description="矩形透明度。", field_type="limited", default=0.22, min_value=0.0, max_value=1.0, step=0.01),
                ExtensionConfigField(key="fill", description="是否填充矩形内部。", field_type="boolean", default=False),
            ],
        )
    )