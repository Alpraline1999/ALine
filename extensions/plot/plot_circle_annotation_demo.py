from matplotlib.patches import Circle

from core.extension_api import ExtensionConfigField, PlotExtension


def _as_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def draw_circle_annotation(plot_context, options):
    axis = plot_context.axis or (plot_context.axes[0] if plot_context.axes else None)
    if axis is None:
        return

    transform = axis.transData if str(options.get("coordinate_mode", "axes_fraction")).strip().lower() == "data" else axis.transAxes
    center_x = _as_float(options.get("center_x", 0.5), 0.5)
    center_y = _as_float(options.get("center_y", 0.5), 0.5)
    radius = max(0.0, _as_float(options.get("radius", 0.12), 0.12))
    alpha = min(1.0, max(0.0, _as_float(options.get("alpha", 0.22), 0.22)))
    fill = bool(options.get("fill", False))
    facecolor = str(options.get("face_color", "#ffd966")) if fill else "none"

    patch = Circle(
        (center_x, center_y),
        radius,
        transform=transform,
        facecolor=facecolor,
        edgecolor=str(options.get("edge_color", "#ff8c00")),
        linewidth=max(0.1, _as_float(options.get("line_width", 1.6), 1.6)),
        linestyle=str(options.get("line_style", "--")),
        alpha=alpha,
        fill=fill,
        clip_on=False,
    )
    axis.add_patch(patch)


def register_extensions(registry):
    registry.register_plot(
        PlotExtension(
            type="plot_circle_annotation",
            name="圆形框",
            handler=draw_circle_annotation,
            description="在图中绘制圆形框，适合圈出局部特征。",
            version="0.1.0",
            settings=True,
            source_kind="builtin",
            config_fields=[
                ExtensionConfigField(key="coordinate_mode", description="坐标模式：axes_fraction 使用画布比例坐标，data 使用数据坐标。", field_type="selective", default="axes_fraction", choices=("axes_fraction", "data")),
                ExtensionConfigField(key="center_x", description="圆心 X。", field_type="number", default=0.5),
                ExtensionConfigField(key="center_y", description="圆心 Y。", field_type="number", default=0.5),
                ExtensionConfigField(key="radius", description="圆半径。", field_type="number", default=0.12),
                ExtensionConfigField(key="edge_color", description="边框颜色。", field_type="color", default="#ff8c00"),
                ExtensionConfigField(key="face_color", description="填充颜色。", field_type="color", default="#ffd966"),
                ExtensionConfigField(key="line_width", description="边框线宽。", field_type="number", default=1.6),
                ExtensionConfigField(key="line_style", description="边框线型。", field_type="selective", default="--", choices=("-", "--", "-.", ":")),
                ExtensionConfigField(key="alpha", description="圆形框透明度。", field_type="limited", default=0.22, min_value=0.0, max_value=1.0, step=0.01),
                ExtensionConfigField(key="fill", description="是否填充圆形框内部。", field_type="boolean", default=False),
            ],
        )
    )