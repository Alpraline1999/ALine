from __future__ import annotations

import numpy as np

from core.extension_api import AnalysisExtension, ExtensionConfigField
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, align_lines_to_common_x, line_from_xy, line_xy, normalize_lines


def _handler(lines, params):
    normalized_lines = normalize_lines(lines)
    if len(normalized_lines) < 2:
        raise ValueError("area_between_curves 需要两条输入曲线")
    options = dict(params or {})
    aligned_lines, warnings = align_lines_to_common_x(normalized_lines[:2], options)
    if len(aligned_lines) < 2:
        raise ValueError("对齐后有效曲线不足 2 条")
    x_values, left_y = line_xy(aligned_lines[0])
    _right_x, right_y = line_xy(aligned_lines[1])
    x_array = np.asarray(list(x_values), dtype=float)
    left_array = np.asarray(list(left_y), dtype=float)
    right_array = np.asarray(list(right_y), dtype=float)
    diff = left_array - right_array
    mode = str(options.get("mode", "absolute") or "absolute").strip().lower()
    integrand = np.abs(diff) if mode == "absolute" else diff
    area = float(np.trapezoid(integrand, x_array))
    result = {
        "analysis_type": "area_between_curves",
        "mode": mode,
        "area": area,
        "alignment_note": warnings[0] if warnings else "",
        "summary_items": [
            {"label": "面积模式", "value": "绝对面积" if mode == "absolute" else "有符号面积"},
            {"label": "面积", "value": area},
        ],
        "lines": [
            {"line_name": "差值曲线", "line": line_from_xy(x_array.tolist(), diff.tolist())},
        ],
        "_plot_series": [
            {"name": "差值曲线", "line": "差值曲线", "color": "#0078D4", "line_width": 1.4},
        ],
    }
    if warnings:
        result["summary_items"].append({"label": "对齐说明", "value": warnings[0]})
    return result


def register_extensions(registry) -> None:
    registry.register_analysis(
        AnalysisExtension(
            type="area_between_curves",
            name="曲线间面积",
            handler=_handler,
            description="计算两条曲线之间的绝对面积或有符号面积。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(2, 2),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(key="mode", label="面积模式", field_type="selective", default="absolute", choices=("absolute", "signed")),
                ExtensionConfigField(key="align_mode", label="对齐方式", field_type="selective", default="auto", choices=("auto", "strict")),
                ExtensionConfigField(key="resample_mode", label="重采样方式", field_type="selective", default="count", choices=("count", "spacing")),
                ExtensionConfigField(key="n", label="对齐点数", field_type="integer", default=400, min_value=2),
                ExtensionConfigField(key="step", label="对齐步长", field_type="number", default=0.1, min_value=0.0, step=0.1),
            ],
        )
    )
