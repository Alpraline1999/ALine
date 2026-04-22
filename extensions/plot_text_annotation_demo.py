from core.extension_api import ExtensionConfigField, PlotExtension


def _as_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def draw_text_annotation(plot_context, options):
    axis = plot_context.axis or (plot_context.axes[0] if plot_context.axes else None)
    if axis is None:
        return

    transform = axis.transData if str(options.get("coordinate_mode", "axes_fraction")).strip().lower() == "data" else axis.transAxes
    x = _as_float(options.get("x", 0.08), 0.08)
    y = _as_float(options.get("y", 0.9), 0.9)
    color = str(options.get("color", "#222222"))
    alpha = min(1.0, max(0.0, _as_float(options.get("alpha", 0.95), 0.95)))
    font_size = max(6, int(_as_float(options.get("font_size", 11), 11)))
    text = str(options.get("text", "请在这里补充说明"))
    bbox_enabled = bool(options.get("show_box", True))

    axis.text(
        x,
        y,
        text,
        transform=transform,
        color=color,
        fontsize=font_size,
        alpha=alpha,
        rotation=_as_float(options.get("rotation", 0.0), 0.0),
        ha=str(options.get("horizontal_align", "left")),
        va=str(options.get("vertical_align", "center")),
        bbox={"boxstyle": "round,pad=0.25", "fc": "#ffffff", "ec": color, "alpha": 0.82} if bbox_enabled else None,
    )


def register_extensions(registry):
    registry.register_plot(
        PlotExtension(
            type="plot_text_annotation",
            name="文字",
            handler=draw_text_annotation,
            description="在图中添加一段文字，可用于备注说明或结论标注。",
            default_options={
                "coordinate_mode": "axes_fraction",
                "x": 0.08,
                "y": 0.9,
                "text": "请在这里补充说明",
                "color": "#222222",
                "font_size": 11,
                "rotation": 0.0,
                "horizontal_align": "left",
                "vertical_align": "center",
                "alpha": 0.95,
                "show_box": True,
            },
            config_fields=[
                ExtensionConfigField(key="coordinate_mode", description="坐标模式：axes_fraction 使用画布比例坐标，data 使用数据坐标。", field_type="string", default="axes_fraction", choices=("axes_fraction", "data")),
                ExtensionConfigField(key="x", description="文本位置 X。", field_type="number", default=0.08),
                ExtensionConfigField(key="y", description="文本位置 Y。", field_type="number", default=0.9),
                ExtensionConfigField(key="text", description="显示的文本内容。", field_type="string", default="请在这里补充说明"),
                ExtensionConfigField(key="color", description="文本颜色。", field_type="string", default="#222222"),
            ],
        )
    )