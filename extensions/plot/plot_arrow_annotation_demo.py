from core.extension_api import ExtensionConfigField, PlotExtension


def _as_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _coord_system(options):
    return "data" if str(options.get("coordinate_mode", "axes_fraction")).strip().lower() == "data" else "axes fraction"


def draw_arrow_annotation(plot_context, options):
    axis = plot_context.axis or (plot_context.axes[0] if plot_context.axes else None)
    if axis is None:
        return

    coord_system = _coord_system(options)
    start_x = _as_float(options.get("start_x", 0.18), 0.18)
    start_y = _as_float(options.get("start_y", 0.82), 0.82)
    end_x = _as_float(options.get("end_x", 0.72), 0.72)
    end_y = _as_float(options.get("end_y", 0.24), 0.24)
    color = str(options.get("color", "#D13438"))
    text = str(options.get("text", "关键趋势"))
    text_color = str(options.get("text_color", color))
    alpha = min(1.0, max(0.0, _as_float(options.get("alpha", 0.95), 0.95)))
    line_width = max(0.1, _as_float(options.get("line_width", 1.8), 1.8))
    font_size = max(6, int(_as_float(options.get("font_size", 11), 11)))

    bbox = None
    if text:
        bbox = {"boxstyle": "round,pad=0.25", "fc": "#ffffff", "ec": color, "alpha": 0.85}

    axis.annotate(
        text,
        xy=(end_x, end_y),
        xytext=(start_x, start_y),
        xycoords=coord_system,
        textcoords=coord_system,
        color=text_color,
        fontsize=font_size,
        bbox=bbox,
        arrowprops={
            "arrowstyle": str(options.get("arrow_style", "->")),
            "color": color,
            "linewidth": line_width,
            "alpha": alpha,
        },
    )


def register_extensions(registry):
    registry.register_plot(
        PlotExtension(
            type="plot_arrow_annotation",
            name="绘制箭头",
            handler=draw_arrow_annotation,
            settings=True,
            description="在图中添加一根箭头，可用于强调趋势或关键点。",
            version="0.1.0",
            config_fields=[
                ExtensionConfigField(key="coordinate_mode", description="坐标模式：axes_fraction 使用画布比例坐标，data 使用数据坐标。", field_type="selective", default="axes_fraction", choices=("axes_fraction", "data")),
                ExtensionConfigField(key="start_x", description="箭头起点 X。", field_type="number", default=0.18),
                ExtensionConfigField(key="start_y", description="箭头起点 Y。", field_type="number", default=0.82),
                ExtensionConfigField(key="end_x", description="箭头终点 X。", field_type="number", default=0.72),
                ExtensionConfigField(key="end_y", description="箭头终点 Y。", field_type="number", default=0.24),
                ExtensionConfigField(key="text", description="箭头文本。", field_type="string", default="关键趋势"),
                ExtensionConfigField(key="color", description="箭头颜色。", field_type="color", default="#D13438"),
                ExtensionConfigField(key="text_color", description="文字颜色。", field_type="color", default="#D13438"),
                ExtensionConfigField(key="arrow_style", description="箭头样式。", field_type="selective", default="->", choices=("->", "-|>", "<->", "<|-|>")),
                ExtensionConfigField(key="line_width", description="箭头线宽。", field_type="number", default=1.8),
                ExtensionConfigField(key="alpha", description="箭头透明度。", field_type="limited", default=0.95, min_value=0.0, max_value=1.0, step=0.01),
                ExtensionConfigField(key="font_size", description="文字字号。", field_type="integer", default=11),
            ],
        )
    )