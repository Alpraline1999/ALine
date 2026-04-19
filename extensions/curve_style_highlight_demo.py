from core.extension_api import CurveStyleExtension, ExtensionConfigField


def apply_highlight_style(style, options):
    updated = dict(style)
    updated["color"] = str(options.get("color", updated.get("color") or "#D96C06"))
    updated["linestyle"] = str(options.get("linestyle", updated.get("linestyle") or "-."))
    updated["linewidth"] = float(options.get("linewidth", updated.get("linewidth", 2.4)))
    updated["marker"] = str(options.get("marker", updated.get("marker") or "o"))
    updated["alpha"] = float(options.get("alpha", updated.get("alpha", 0.9)))
    updated["markevery"] = max(1, int(float(options.get("markevery", updated.get("markevery", 2)))))
    return updated


def register_extensions(registry):
    registry.register_curve_style(
        CurveStyleExtension(
            type="demo_curve_style_highlight",
            name="示例·高亮曲线",
            handler=apply_highlight_style,
            description="让当前曲线更醒目，适合突出关键测点。",
            default_options={
                "color": "#D96C06",
                "linestyle": "-.",
                "linewidth": 2.4,
                "marker": "o",
                "alpha": 0.9,
                "markevery": 2,
            },
            config_fields=[
                ExtensionConfigField(
                    key="color",
                    label="颜色",
                    description="曲线颜色。",
                    field_type="string",
                    default="#D96C06",
                ),
                ExtensionConfigField(
                    key="linestyle",
                    label="线型",
                    description="matplotlib 线型字符串。",
                    field_type="string",
                    default="-.",
                ),
                ExtensionConfigField(
                    key="linewidth",
                    label="线宽",
                    description="应用后的曲线线宽。",
                    field_type="number",
                    default=2.4,
                ),
                ExtensionConfigField(
                    key="marker",
                    label="点样式",
                    description="matplotlib marker 字符串。",
                    field_type="string",
                    default="o",
                ),
                ExtensionConfigField(
                    key="alpha",
                    label="透明度",
                    description="曲线透明度。",
                    field_type="number",
                    default=0.9,
                ),
                ExtensionConfigField(
                    key="markevery",
                    label="采样点间隔",
                    description="每隔多少个点绘制一个 marker。",
                    field_type="integer",
                    default=2,
                ),
            ],
        )
    )