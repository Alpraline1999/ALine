from core.extension_api import ExtensionConfigField, PlotExtension


def draw_reference_line(axis, series, options):
    values = []
    for item in series:
        values.extend(float(value) for value in item.get("y", []))
    if not values:
        return
    level = sum(values) / len(values) + float(options.get("offset", 0.0))
    axis.axhline(
        level,
        color=str(options.get("color", "#C23B22")),
        linestyle=str(options.get("linestyle", "--")),
        linewidth=float(options.get("linewidth", 1.2)),
        alpha=float(options.get("alpha", 0.8)),
        label=str(options.get("label", "Reference")),
    )


def register_extensions(registry):
    registry.register_plot(
        PlotExtension(
            type="demo_plot_reference_line",
            name="示例·参考线",
            handler=draw_reference_line,
            description="按当前曲线均值绘制一条可偏移的水平参考线。",
            default_options={
                "color": "#C23B22",
                "linestyle": "--",
                "linewidth": 1.2,
                "alpha": 0.8,
                "offset": 0.0,
                "label": "Reference",
            },
            config_fields=[
                ExtensionConfigField(
                    key="color",
                    label="颜色",
                    description="参考线颜色。",
                    field_type="string",
                    default="#C23B22",
                ),
                ExtensionConfigField(
                    key="linestyle",
                    label="线型",
                    description="matplotlib 线型字符串。",
                    field_type="string",
                    default="--",
                ),
                ExtensionConfigField(
                    key="linewidth",
                    label="线宽",
                    description="参考线宽度。",
                    field_type="number",
                    default=1.2,
                ),
                ExtensionConfigField(
                    key="alpha",
                    label="透明度",
                    description="参考线透明度。",
                    field_type="number",
                    default=0.8,
                ),
                ExtensionConfigField(
                    key="offset",
                    label="Y 偏移",
                    description="在均值基础上额外增加的偏移量。",
                    field_type="number",
                    default=0.0,
                ),
                ExtensionConfigField(
                    key="label",
                    label="图例文本",
                    description="添加到图例中的名称。",
                    field_type="string",
                    default="Reference",
                ),
            ],
        )
    )