from core.extension_api import ExtensionConfigField, ProcessingExtension


def scale_y_values(xs, ys, params):
    factor = float(params.get("factor", 1.5))
    baseline = float(params.get("baseline", 0.0))
    return list(xs), [baseline + float(value) * factor for value in ys]


def register_extensions(registry):
    registry.register_processing(
        ProcessingExtension(
            type="demo_processing_scale",
            name="示例·Y缩放",
            handler=scale_y_values,
            description="按倍率缩放 Y 值，并可叠加一个基线偏移。",
            default_options={"factor": 1.5, "baseline": 0.0},
            config_fields=[
                ExtensionConfigField(
                    key="factor",
                    description="把当前 Y 值乘以这个倍率。",
                    field_type="number",
                    default=1.5,
                ),
                ExtensionConfigField(
                    key="baseline",
                    description="在缩放后额外加到每个 Y 值上的偏移量。",
                    field_type="number",
                    default=0.0,
                ),
            ],
        )
    )