from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.extension_api import ExtensionConfigField, ProcessingExtension
from core.line_tools import (
    BUILTIN_EXTENSION_VERSION,
    line_from_xy,
    line_xy,
    primary_line,
    resample_to_grid,
    resample_uniform,
    resample_uniform_spacing,
    sorted_unique_xy,
    x_values_equal,
)


def _resample_xy(
    line: Any,
    params: Optional[Dict[str, Any]] = None,
    *,
    lines: Optional[List[Any]] = None,
):
    xs, ys = line_xy(line)
    options = dict(params or {})
    x_sorted, y_sorted = sorted_unique_xy(xs, ys)
    if len(x_sorted) < 2:
        return line_from_xy(xs, ys)

    mode = str(options.get("mode", "spacing") or "spacing").strip().lower()
    if mode == "align":
        pool = list(lines or [])
        try:
            target_idx = int(options.get("target_line", options.get("target_index", 1)) or 1)
        except Exception:
            target_idx = 1
        if target_idx < 1 or target_idx > len(pool):
            return line_from_xy(x_sorted, y_sorted)
        target_x, _target_y = line_xy(pool[target_idx - 1])
        if not target_x or x_values_equal(x_sorted, target_x):
            return line_from_xy(x_sorted, y_sorted)
        algorithm = str(options.get("algorithm", "linear") or "linear").strip().lower()
        return line_from_xy(list(target_x), resample_to_grid(x_sorted, y_sorted, target_x, algorithm))

    if mode == "spacing":
        spacing_mode = str(options.get("spacing_mode", "") or "").strip().lower()
        if not spacing_mode:
            spacing_mode = "coord" if ("step" in options or "spacing" in options) else "point"
        if spacing_mode == "coord":
            spacing = float(options.get("step", options.get("spacing", 0.0)) or 0.0)
            if spacing <= 0:
                raise ValueError("坐标间距必须大于 0")
            nx, ny = resample_uniform_spacing(x_sorted, y_sorted, spacing)
            return line_from_xy(nx, ny)
        nx, ny = resample_uniform(x_sorted, y_sorted, max(2, int(options.get("n", 200) or 200)))
        return line_from_xy(nx, ny)

    nx, ny = resample_uniform(x_sorted, y_sorted, max(2, int(options.get("n", 200) or 200)))
    return line_from_xy(nx, ny)


def resample_handler(lines, params):
    return _resample_xy(primary_line(lines), params, lines=lines)


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="resample",
            name="重采样",
            handler=resample_handler,
            description="支持按点数或间距重采样，便于多曲线对齐。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(
                    key="algorithm",
                    label="插值算法",
                    field_type="selective",
                    default="linear",
                    choices=["linear", "nearest", "cubic"],
                ),
                ExtensionConfigField(
                    key="mode",
                    label="重采样模式",
                    field_type="selective",
                    default="spacing",
                    choices=["spacing", "align"],
                ),
                ExtensionConfigField(
                    key="spacing_mode",
                    label="间距方式",
                    field_type="selective",
                    default="point",
                    choices=["point", "coord"],
                ),
                ExtensionConfigField(key="n", label="目标点数", field_type="integer", default=200, min_value=2),
                ExtensionConfigField(key="step", label="目标步长", field_type="number", default=1.0),
                ExtensionConfigField(
                    key="target_line",
                    label="对齐曲线",
                    field_type="line",
                    default=1,
                    description="从当前数据集中选择 1 条曲线作为对齐参考。",
                ),
            ],
        )
    )
