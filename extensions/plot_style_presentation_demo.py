from core.extension_api import ExtensionConfigField, PlotStyleExtension


def apply_presentation_style(state, options):
    updated = dict(state)
    updated["grid"] = bool(options.get("grid", True))
    updated["grid_alpha"] = float(options.get("grid_alpha", 0.28))
    updated["line_width"] = float(options.get("line_width", 2.2))
    updated["marker_size"] = float(options.get("marker_size", 5.5))
    return updated


def register_extensions(registry):
    registry.register_plot_style(
        PlotStyleExtension(
            type="demo_plot_style_presentation",
            name="扩展示例样式",
            handler=apply_presentation_style,
            description="提高线宽和点大小，并启用较柔和的网格透明度。",
            default_options={
                "grid": True,
                "grid_alpha": 0.28,
                "line_width": 2.2,
                "marker_size": 5.5,
            },
            config_fields=[
                ExtensionConfigField(
                    key="grid",
                    label="显示网格",
                    description="是否启用网格。",
                    field_type="boolean",
                    default=True,
                ),
                ExtensionConfigField(
                    key="grid_alpha",
                    label="网格透明度",
                    description="0 到 1 之间的透明度值。",
                    field_type="number",
                    default=0.28,
                ),
                ExtensionConfigField(
                    key="line_width",
                    label="线宽",
                    description="应用后的整体线宽。",
                    field_type="number",
                    default=2.2,
                ),
                ExtensionConfigField(
                    key="marker_size",
                    label="点大小",
                    description="应用后的整体点大小。",
                    field_type="number",
                    default=5.5,
                ),
            ],
        )
    )