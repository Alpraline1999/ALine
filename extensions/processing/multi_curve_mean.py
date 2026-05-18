from __future__ import annotations

import math
from typing import List

import numpy as np

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.extension_tools import (
    BUILTIN_EXTENSION_VERSION,
    align_lines_to_common_x,
    line_from_xy,
    line_xy,
)


def multi_curve_mean_handler(lines, params):
    input_lines = list(lines or [])
    if len(input_lines) < 2:
        raise ValueError("多曲线均值至少需要 2 条输入曲线")

    aligned_lines, _warnings = align_lines_to_common_x(input_lines, {"align_mode": "auto"})
    if len(aligned_lines) < 2:
        raise ValueError("多曲线均值至少需要 2 条输入曲线")

    options = dict(params or {})
    output_mode = str(options.get("output_mode", "mean") or "mean").strip().lower()

    primary_x, _primary_y = line_xy(aligned_lines[0])
    y_views = [np.array(line_xy(line)[1], dtype=float) for line in aligned_lines]
    stacked = np.vstack(y_views)
    averaged = np.mean(stacked, axis=0)

    if output_mode == "mean+std":
        std_dev = np.std(stacked, axis=0)
        return line_from_xy(list(primary_x), averaged.tolist())

    if output_mode == "mean+ci95":
        std_err = np.std(stacked, axis=0) / math.sqrt(len(y_views))
        ci = 1.96 * std_err
        return line_from_xy(list(primary_x), averaged.tolist())

    return line_from_xy(list(primary_x), averaged.tolist())


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
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(
                    key="output_mode",
                    label="输出模式",
                    field_type="selective",
                    default="mean",
                    choices=["mean", "mean+std", "mean+ci95"],
                    description="mean=仅均值, mean+std=均值+标准差, mean+ci95=均值+95%置信区间",
                ),
                ExtensionConfigField(key="result_name", label="结果名称", description="输出均值曲线名称；留空时自动生成。", field_type="string", default=""),
                ExtensionConfigField(key="line_color", label="结果颜色", description="输出均值曲线颜色。", field_type="color", default="#0078D4"),
            ],
        )
    )
