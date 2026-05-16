from __future__ import annotations

from typing import List

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.extension_tools import align_lines_to_common_x, BUILTIN_EXTENSION_VERSION, line_from_xy, line_xy


def multi_curve_mean_handler(lines, params):
    input_lines = list(lines or [])
    if len(input_lines) < 2:
        raise ValueError("多曲线均值至少需要 2 条输入曲线")

    aligned_lines, _warnings = align_lines_to_common_x(input_lines, {"align_mode": "auto"})
    if len(aligned_lines) < 2:
        raise ValueError("多曲线均值至少需要 2 条输入曲线")

    primary_x, _primary_y = line_xy(aligned_lines[0])
    y_views = [line_xy(line)[1] for line in aligned_lines]
    averaged: List[float]
    try:
        import numpy as np

        averaged = np.mean(
            np.vstack([view.to_numpy(copy=False) for view in y_views]),
            axis=0,
        ).tolist()
    except Exception:
        averaged = [
            sum(float(value) for value in row) / len(y_views)
            for row in zip(*(list(view) for view in y_views))
        ]

    return line_from_xy(list(primary_x), averaged)


def register_extensions(registry):
    registry.register_processing(
        ProcessingExtension(
            type="multi_curve_mean",
            name="多曲线均值",
            handler=multi_curve_mean_handler,
            description="对多条输入曲线计算逐点均值；曲线会自动对齐到公共 X 网格。",
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
