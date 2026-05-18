from __future__ import annotations

from collections import defaultdict
from statistics import median

from core.extension_api import ExtensionConfigField, ProcessingExtension
from core.line_tools import resample_uniform, resample_uniform_spacing
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy, line_xy, primary_line


def _aggregate(values, mode: str) -> float:
    if not values:
        return 0.0
    if mode == "median":
        return float(median(values))
    if mode == "min":
        return float(min(values))
    if mode == "max":
        return float(max(values))
    if mode == "last":
        return float(values[-1])
    return float(sum(values) / len(values))


def _handler(lines, params):
    xs, ys = line_xy(primary_line(lines))
    if not xs or not ys:
        return line_from_xy(list(xs), list(ys))
    options = dict(params or {})
    dedup_mode = str(options.get("dedup_mode", "mean") or "mean").strip().lower()
    buckets = defaultdict(list)
    for x_value, y_value in zip(xs, ys):
        buckets[float(x_value)].append(float(y_value))
    unique_x = sorted(buckets)
    unique_y = [_aggregate(buckets[x_value], dedup_mode) for x_value in unique_x]
    spacing = float(options.get("target_spacing", 0.0) or 0.0)
    target_count = max(0, int(options.get("target_count", 0) or 0))
    if spacing > 0 and len(unique_x) >= 2:
        unique_x, unique_y = resample_uniform_spacing(unique_x, unique_y, spacing)
    elif target_count >= 2 and len(unique_x) >= 2:
        unique_x, unique_y = resample_uniform(unique_x, unique_y, target_count)
    return line_from_xy(list(unique_x), list(unique_y))


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="sort_dedup_interpolate",
            name="排序去重插值",
            handler=_handler,
            description="按 X 排序、合并重复 X 点，并可按步长或点数重新插值。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(key="dedup_mode", label="重复点合并", field_type="selective", default="mean", choices=("mean", "median", "last", "min", "max")),
                ExtensionConfigField(key="target_spacing", label="目标步长", field_type="number", default=0.0, min_value=0.0, step=0.1),
                ExtensionConfigField(key="target_count", label="目标点数", field_type="integer", default=0, min_value=0),
            ],
        )
    )
