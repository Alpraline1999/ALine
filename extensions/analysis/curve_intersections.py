from __future__ import annotations

from core.extension_api import AnalysisExtension, ExtensionConfigField
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, align_lines_to_common_x, line_from_xy, line_xy, normalize_lines


def _intersections_from_aligned(x_values, left_y, right_y):
    points = []
    for index in range(len(x_values) - 1):
        x1 = float(x_values[index])
        x2 = float(x_values[index + 1])
        d1 = float(left_y[index] - right_y[index])
        d2 = float(left_y[index + 1] - right_y[index + 1])
        if d1 == 0.0:
            points.append((x1, float((left_y[index] + right_y[index]) / 2.0)))
            continue
        if d1 * d2 > 0:
            continue
        span = d2 - d1
        ratio = 0.0 if span == 0 else (0.0 - d1) / span
        x_value = x1 + ratio * (x2 - x1)
        y_left = float(left_y[index] + ratio * (left_y[index + 1] - left_y[index]))
        y_right = float(right_y[index] + ratio * (right_y[index + 1] - right_y[index]))
        points.append((float(x_value), float((y_left + y_right) / 2.0)))
    unique = []
    for point in points:
        if unique and abs(point[0] - unique[-1][0]) <= 1e-9:
            continue
        unique.append(point)
    return unique


def _handler(lines, params):
    normalized_lines = normalize_lines(lines)
    if len(normalized_lines) < 2:
        raise ValueError("curve_intersections 需要两条输入曲线")
    options = dict(params or {})
    aligned_lines, warnings = align_lines_to_common_x(normalized_lines[:2], options)
    if len(aligned_lines) < 2:
        raise ValueError("对齐后有效曲线不足 2 条")
    x_values, left_y = line_xy(aligned_lines[0])
    _right_x, right_y = line_xy(aligned_lines[1])
    points = _intersections_from_aligned(list(x_values), list(left_y), list(right_y))
    intersection_line = line_from_xy([item[0] for item in points], [item[1] for item in points]) if points else []
    result = {
        "analysis_type": "curve_intersections",
        "intersection_count": len(points),
        "alignment_note": warnings[0] if warnings else "",
        "summary_items": [
            {"label": "交点数量", "value": len(points)},
        ],
        "tables": [
            {
                "title": "交点列表",
                "headers": ["序号", "X", "Y"],
                "rows": [[index + 1, point[0], point[1]] for index, point in enumerate(points)],
            }
        ] if points else [],
    }
    if warnings:
        result["summary_items"].append({"label": "对齐说明", "value": warnings[0]})
    if points:
        result["lines"] = [{"line_name": "交点", "line": intersection_line}]
        result["_plot_series"] = [{"name": "交点", "line": "交点", "kind": "markers", "marker": "o", "size": 48, "color": "#D13438"}]
    return result


def register_extensions(registry) -> None:
    registry.register_analysis(
        AnalysisExtension(
            type="curve_intersections",
            name="曲线交点",
            handler=_handler,
            description="对两条曲线自动对齐后查找交点，并输出交点列表与标记。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(2, 2),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(key="align_mode", label="对齐方式", field_type="selective", default="auto", choices=("auto", "strict")),
                ExtensionConfigField(key="resample_mode", label="重采样方式", field_type="selective", default="count", choices=("count", "spacing")),
                ExtensionConfigField(key="n", label="对齐点数", field_type="integer", default=400, min_value=2),
                ExtensionConfigField(key="step", label="对齐步长", field_type="number", default=0.1, min_value=0.0, step=0.1),
            ],
        )
    )
