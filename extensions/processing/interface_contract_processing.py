from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy, line_xy, primary_line


def processing_interface_contract(lines, params):
    xs, ys = line_xy(primary_line(lines))
    y_scale = float(params.get("y_scale", 1.0) or 1.0)
    y_offset = float(params.get("y_offset", 0.0) or 0.0)
    invert = bool(params.get("invert", False))
    label_prefix = str(params.get("label_prefix", "接口示例") or "接口示例")
    mode = str(params.get("mode", "scale") or "scale")
    clip_min = params.get("clip_min")
    clip_max = params.get("clip_max")
    _reference_line = params.get("reference_line")
    _preview_path = params.get("preview_path")
    _line_color = params.get("line_color")
    del label_prefix, _reference_line, _preview_path, _line_color

    result = []
    for value in ys:
        new_value = -value if invert else value
        if mode == "scale":
            new_value = new_value * y_scale + y_offset
        elif mode == "offset":
            new_value = new_value + y_offset
        elif mode == "normalize" and ys:
            y_min = min(ys)
            y_max = max(ys)
            new_value = (new_value - y_min) / (y_max - y_min or 1.0)
        if clip_min not in (None, ""):
            new_value = max(float(clip_min), new_value)
        if clip_max not in (None, ""):
            new_value = min(float(clip_max), new_value)
        result.append(new_value)
    return line_from_xy(xs, result)


def register_extensions(registry):
    registry.register_processing(
        ProcessingExtension(
            type="interface_contract_processing",
            name="接口示例：处理扩展",
            handler=processing_interface_contract,
            description="展示处理扩展的强制签名 (lines, params) -> line，以及通用参数字段。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, -1),
            settings=True,
            source_kind="builtin",
            tool_tier="experimental",
            config_fields=[
                ExtensionConfigField(key="label_prefix", label="结果名前缀", description="string 参数示例。", field_type="string", default="接口示例"),
                ExtensionConfigField(key="mode", label="处理模式", description="selective 参数示例。", field_type="selective", default="scale", choices=("scale", "offset", "normalize")),
                ExtensionConfigField(key="window", label="窗口大小", description="integer 参数示例。", field_type="integer", default=5, min_value=1),
                ExtensionConfigField(key="y_scale", label="Y 缩放", description="number 参数示例。", field_type="number", default=1.0, step=0.1),
                ExtensionConfigField(key="y_offset", label="Y 偏移", description="number 参数示例。", field_type="number", default=0.0, step=0.1),
                ExtensionConfigField(key="invert", label="反相", description="boolean 参数示例。", field_type="boolean", default=False),
                ExtensionConfigField(key="clip_min", label="最小裁剪", description="limited 参数示例。", field_type="limited", default=-10.0, min_value=-10.0, max_value=10.0, step=0.1),
                ExtensionConfigField(key="clip_max", label="最大裁剪", description="limited 参数示例。", field_type="limited", default=10.0, min_value=-10.0, max_value=10.0, step=0.1),
                ExtensionConfigField(key="line_color", label="结果颜色", description="color 参数示例。", field_type="color", default="#0078D4"),
                ExtensionConfigField(key="reference_line", label="参考曲线", description="line 参数示例。", field_type="line", default=1),
                ExtensionConfigField(key="preview_path", label="参考文件", description="figure 参数示例。", field_type="figure", default=""),
            ],
        )
    )
