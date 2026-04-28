from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.extension_tools import align_lines_to_common_x, BUILTIN_EXTENSION_VERSION, line_from_xy, line_xy, normalize_lines


def multi_curve_mean_handler(lines, params):
    del params
    input_lines = normalize_lines(lines)
    aligned_lines, warnings = align_lines_to_common_x(input_lines, {"align_mode": "strict"})
    if len(aligned_lines) < 2:
        raise ValueError("多曲线均值至少需要 2 条输入曲线")

    primary_x, _primary_y = line_xy(aligned_lines[0])
    point_count = len(primary_x)
    averaged = []
    for index in range(point_count):
        averaged.append(sum(float(line_xy(line)[1][index]) for line in aligned_lines) / len(aligned_lines))

    if warnings:
        # strict line 协议下不再返回 warnings；对齐说明由运行时或上层界面处理。
        pass
    return line_from_xy(primary_x, averaged)


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