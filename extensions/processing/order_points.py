from __future__ import annotations

from statistics import median

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy, line_xy, primary_line


def _merge_group(points, axis: str, mode: str):
    if not points:
        return None
    xs = [float(item[0]) for item in points]
    ys = [float(item[1]) for item in points]
    if mode == "median":
        return [float(median(xs)), float(median(ys))]
    if mode == "first":
        return list(points[0])
    if mode == "last":
        return list(points[-1])
    if mode == "min":
        return [float(min(xs)), float(min(ys))]
    if mode == "max":
        return [float(max(xs)), float(max(ys))]
    return [float(sum(xs) / len(xs)), float(sum(ys) / len(ys))]


def _handler(lines, params):
    xs, ys = line_xy(primary_line(lines))
    points = [[float(x_value), float(y_value)] for x_value, y_value in zip(xs, ys)]
    if len(points) < 2:
        return line_from_xy(list(xs), list(ys))
    options = dict(params or {})
    axis = "y" if str(options.get("axis", "x") or "x").strip().lower() == "y" else "x"
    reverse = str(options.get("direction", "ascending") or "ascending").strip().lower() == "descending"
    merge_mode = str(options.get("merge_mode", "keep") or "keep").strip().lower()
    tolerance = max(0.0, float(options.get("group_tolerance", 0.0) or 0.0))
    key_index = 1 if axis == "y" else 0
    points.sort(key=lambda item: item[key_index], reverse=reverse)
    if merge_mode == "keep" or tolerance <= 0:
        return line_from_xy([item[0] for item in points], [item[1] for item in points])
    grouped = []
    current_group = [points[0]]
    for point in points[1:]:
        if abs(point[key_index] - current_group[-1][key_index]) <= tolerance:
            current_group.append(point)
            continue
        grouped.append(_merge_group(current_group, axis, merge_mode))
        current_group = [point]
    grouped.append(_merge_group(current_group, axis, merge_mode))
    grouped = [item for item in grouped if item is not None]
    return line_from_xy([item[0] for item in grouped], [item[1] for item in grouped])


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="order_points",
            name="点序整理",
            handler=_handler,
            description="按 X 或 Y 重新排序数字化点，并可按容差合并近邻点。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(key="axis", label="排序轴", field_type="selective", default="x", choices=("x", "y")),
                ExtensionConfigField(key="direction", label="排序方向", field_type="selective", default="ascending", choices=("ascending", "descending")),
                ExtensionConfigField(key="group_tolerance", label="合并容差", field_type="number", default=0.0, min_value=0.0, step=0.1),
                ExtensionConfigField(key="merge_mode", label="合并策略", field_type="selective", default="keep", choices=("keep", "mean", "median", "first", "last", "min", "max")),
            ],
        )
    )
