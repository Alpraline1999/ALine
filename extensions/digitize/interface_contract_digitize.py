from __future__ import annotations

from core.extension_api import DigitizeExtension, ExtensionConfigField
from extensions.processing.extension_tools import line_from_xy


VERSION = "0.1.0"


def digitize_interface_contract(figure, params):
    del figure
    count = max(0, int(params.get("point_count", 3) or 3))
    spacing = max(1.0, float(params.get("spacing", 16.0) or 16.0))
    start_x = float(params.get("start_x", 10.0) or 10.0)
    start_y = float(params.get("start_y", 10.0) or 10.0)
    reverse_y = bool(params.get("reverse_y", False))
    _sampled_color = params.get("sampled_color")
    _template_info = params.get("template_info")
    _reference_figure = params.get("reference_figure")
    del _sampled_color, _template_info, _reference_figure

    xs = [start_x + index * spacing for index in range(count)]
    if reverse_y:
        ys = [start_y - index * spacing for index in range(count)]
    else:
        ys = [start_y + index * spacing for index in range(count)]
    return line_from_xy(xs, ys)


def register_extensions(registry):
    registry.register_digitize(
        DigitizeExtension(
            type="interface_contract_digitize",
            name="接口示例：数字化扩展",
            handler=digitize_interface_contract,
            description="展示数字化扩展的强制签名 (figure, params) -> line，以及 pickcolor / shot 交互字段。",
            version=VERSION,
            settings=True,
            source_kind="builtin",
            tool_tier="experimental",
            hidden=True,
            config_fields=[
                ExtensionConfigField(key="point_count", label="点数量", description="integer 参数示例。", field_type="integer", default=3, min_value=0, max_value=100),
                ExtensionConfigField(key="spacing", label="点间距", description="number 参数示例。", field_type="number", default=16.0, min_value=1.0, step=1.0),
                ExtensionConfigField(key="start_x", label="起点 X", description="number 参数示例。", field_type="number", default=10.0, step=1.0),
                ExtensionConfigField(key="start_y", label="起点 Y", description="number 参数示例。", field_type="number", default=10.0, step=1.0),
                ExtensionConfigField(key="reverse_y", label="Y 反向", description="boolean 参数示例。", field_type="boolean", default=False),
                ExtensionConfigField(key="sampled_color", label="采样颜色", description="pickcolor 参数示例。", field_type="pickcolor", default={"r": 0, "g": 120, "b": 212}),
                ExtensionConfigField(key="template_info", label="模板截图", description="shot 参数示例。", field_type="shot", default=None),
                ExtensionConfigField(key="reference_figure", label="参考图片", description="figure 参数示例。", field_type="figure", default=""),
            ],
        )
    )
