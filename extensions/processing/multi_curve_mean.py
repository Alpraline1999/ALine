from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from processing.data_engine import align_lines_to_common_x
from processing.extension_tools import BUILTIN_EXTENSION_VERSION, coerce_processing_handler_call


def multi_curve_mean_handler(inputs_or_xs, ys_or_params=None, params=None, lines=None):
    input_lines, options = coerce_processing_handler_call(inputs_or_xs, ys_or_params, params, lines=lines)
    aligned_lines, warnings = align_lines_to_common_x(list(input_lines or []), {"align_mode": "strict"})
    if len(aligned_lines) < 2:
        raise ValueError("多曲线均值至少需要 2 条输入曲线")

    point_count = len(aligned_lines[0].get("x", []))
    averaged = []
    for index in range(point_count):
        averaged.append(sum(float(line["y"][index]) for line in aligned_lines) / len(aligned_lines))

    primary = aligned_lines[0]
    result_name = str(options.get("result_name", "") or "").strip() or f"{primary.get('name', 'primary')}_mean"
    line_color = str(options.get("line_color", primary.get("color", "#0078D4")) or primary.get("color", "#0078D4"))
    return {
        "name": result_name,
        "x": list(primary.get("x", [])),
        "y": averaged,
        "x_label": str(primary.get("x_label", "x") or "x"),
        "y_label": str(primary.get("y_label", "y") or "y"),
        "color": line_color,
        "warnings": warnings,
    }


def register_extensions(registry):
    registry.register_processing(
        ProcessingExtension(
            type="multi_curve_mean",
            name="多曲线均值",
            handler=multi_curve_mean_handler,
            description="对多条输入曲线计算逐点均值；要求输入曲线已对齐。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(2, -1),
            settings=True,
            source_kind="builtin",
            tool_tier="experimental",
            config_fields=[
                ExtensionConfigField(key="result_name", label="结果名称", description="输出均值曲线名称；留空时自动生成。", field_type="string", default=""),
                ExtensionConfigField(key="line_color", label="结果颜色", description="输出均值曲线颜色。", field_type="color", default="#0078D4"),
            ],
        )
    )