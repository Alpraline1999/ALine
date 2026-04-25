from core.extension_api import ExtensionConfigField, PlotExtension
from extensions.plot._runtime import current_axis


def _as_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def draw_text_annotation(lines, params):
    del lines
    axis = current_axis()
    if axis is None:
        return

    transform = axis.transData if str(params.get("coordinate_mode", "axes_fraction")).strip().lower() == "data" else axis.transAxes
    x = _as_float(params.get("x", 0.08), 0.08)
    y = _as_float(params.get("y", 0.9), 0.9)
    color = str(params.get("color", "#222222"))
    alpha = min(1.0, max(0.0, _as_float(params.get("alpha", 0.95), 0.95)))
    font_size = max(6, int(_as_float(params.get("font_size", 11), 11)))
    text = str(params.get("text", "请在这里补充说明"))
    bbox_enabled = bool(params.get("show_box", True))

    axis.text(
        x,
        y,
        text,
        transform=transform,
        color=color,
        fontsize=font_size,
        alpha=alpha,
        rotation=_as_float(params.get("rotation", 0.0), 0.0),
        ha=str(params.get("horizontal_align", "left")),
        va=str(params.get("vertical_align", "center")),
        bbox={"boxstyle": "round,pad=0.25", "fc": "#ffffff", "ec": color, "alpha": 0.82} if bbox_enabled else None,
    )


def register_extensions(registry):
    registry.register_plot(
        PlotExtension(
            type="plot_text_annotation",
            name="文字标注",
            handler=draw_text_annotation,
            description="在图中添加一段文字，可用于备注说明或结论标注。",
            version="0.1.0",
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            phases=("after_plot",),
            config_fields=[
                ExtensionConfigField(key="coordinate_mode", description="坐标模式：axes_fraction 使用画布比例坐标，data 使用数据坐标。", field_type="selective", default="axes_fraction", choices=("axes_fraction", "data")),
                ExtensionConfigField(key="x", description="文本位置 X。", field_type="number", default=0.08),
                ExtensionConfigField(key="y", description="文本位置 Y。", field_type="number", default=0.9),
                ExtensionConfigField(key="text", description="显示的文本内容。", field_type="string", default="请在这里补充说明"),
                ExtensionConfigField(key="color", description="文本颜色。", field_type="color", default="#222222"),
                ExtensionConfigField(key="font_size", description="文字字号。", field_type="integer", default=11),
                ExtensionConfigField(key="rotation", description="文字旋转角度。", field_type="number", default=0.0),
                ExtensionConfigField(key="horizontal_align", description="水平对齐方式。", field_type="selective", default="left", choices=("left", "center", "right")),
                ExtensionConfigField(key="vertical_align", description="垂直对齐方式。", field_type="selective", default="center", choices=("top", "center", "bottom", "baseline")),
                ExtensionConfigField(key="alpha", description="文字透明度。", field_type="limited", default=0.95, min_value=0.0, max_value=1.0, step=0.01),
                ExtensionConfigField(key="show_box", description="是否显示文字背景框。", field_type="boolean", default=True),
            ],
        )
    )