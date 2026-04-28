from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy, line_xy, primary_line


XY = Tuple[List[float], List[float]]


def _sorted_unique_xy(xs: List[float], ys: List[float]) -> XY:
    pairs = []
    for x_value, y_value in zip(xs, ys):
        try:
            x_float = float(x_value)
            y_float = float(y_value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(x_float) or not math.isfinite(y_float):
            continue
        pairs.append((x_float, y_float))
    if len(pairs) < 2:
        return list(xs), list(ys)

    pairs.sort(key=lambda item: item[0])
    unique_x: List[float] = []
    unique_y: List[float] = []
    for x_value, y_value in pairs:
        if unique_x and math.isclose(x_value, unique_x[-1], rel_tol=0.0, abs_tol=1e-12):
            unique_y[-1] = y_value
            continue
        unique_x.append(x_value)
        unique_y.append(y_value)
    return unique_x, unique_y


def _interp_linear(x_value: float, xs: List[float], ys: List[float]) -> float:
    if not xs:
        return 0.0
    if x_value <= xs[0]:
        return ys[0]
    if x_value >= xs[-1]:
        return ys[-1]
    lo, hi = 0, len(xs) - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if xs[mid] <= x_value:
            lo = mid
        else:
            hi = mid
    span = xs[hi] - xs[lo]
    if not span:
        return ys[lo]
    ratio = (x_value - xs[lo]) / span
    return ys[lo] + ratio * (ys[hi] - ys[lo])


def _resample_uniform(xs: List[float], ys: List[float], n_points: int) -> XY:
    if len(xs) < 2 or n_points < 2:
        return list(xs), list(ys)
    x_min, x_max = xs[0], xs[-1]
    if math.isclose(x_min, x_max, rel_tol=0.0, abs_tol=1e-12):
        return list(xs), list(ys)
    target_x = [x_min + index * (x_max - x_min) / (n_points - 1) for index in range(n_points)]
    return target_x, [_interp_linear(x_value, xs, ys) for x_value in target_x]


def _resample_uniform_spacing(xs: List[float], ys: List[float], spacing: float) -> XY:
    if len(xs) < 2 or spacing <= 0:
        return list(xs), list(ys)
    x_min, x_max = xs[0], xs[-1]
    if math.isclose(x_min, x_max, rel_tol=0.0, abs_tol=1e-12):
        return list(xs), list(ys)

    target_x = [x_min]
    next_x = x_min + spacing
    while next_x < x_max - 1e-12:
        target_x.append(next_x)
        next_x += spacing
    if not math.isclose(target_x[-1], x_max, rel_tol=0.0, abs_tol=1e-12):
        target_x.append(x_max)
    return target_x, [_interp_linear(x_value, xs, ys) for x_value in target_x]


def _nearest_value(x_value: float, xs: List[float], ys: List[float]) -> float:
    if not xs:
        return 0.0
    best_index = 0
    best_distance = abs(xs[0] - x_value)
    for index in range(1, len(xs)):
        distance = abs(xs[index] - x_value)
        if distance < best_distance:
            best_distance = distance
            best_index = index
    return float(ys[best_index])


def _resample_to_grid(xs: List[float], ys: List[float], target_x: List[float], algorithm: str) -> List[float]:
    mode = str(algorithm or "linear").strip().lower()
    if mode == "nearest":
        return [_nearest_value(float(value), xs, ys) for value in target_x]
    if mode == "cubic":
        try:
            import numpy as np
            from scipy.interpolate import CubicSpline

            spline = CubicSpline(np.asarray(xs, dtype=float), np.asarray(ys, dtype=float), extrapolate=False)
            values = spline(np.asarray(target_x, dtype=float))
            result: List[float] = []
            for raw, fallback_x in zip(values.tolist(), target_x):
                try:
                    raw_value = float(raw)
                except (TypeError, ValueError):
                    raw_value = math.nan
                if math.isnan(raw_value):
                    result.append(_interp_linear(float(fallback_x), xs, ys))
                else:
                    result.append(raw_value)
            return result
        except Exception:
            pass
    return [_interp_linear(float(value), xs, ys) for value in target_x]


def _x_values_equal(left_values: List[float], right_values: List[float]) -> bool:
    if len(left_values) != len(right_values):
        return False
    for left, right in zip(left_values, right_values):
        if not math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12):
            return False
    return True


def _resample_xy(
    line: Any,
    params: Optional[Dict[str, Any]] = None,
    *,
    lines: Optional[List[Any]] = None,
):
    xs, ys = line_xy(line)
    options = dict(params or {})
    x_sorted, y_sorted = _sorted_unique_xy(xs, ys)
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
        if not target_x or _x_values_equal(x_sorted, target_x):
            return line_from_xy(x_sorted, y_sorted)
        algorithm = str(options.get("algorithm", "linear") or "linear").strip().lower()
        return line_from_xy(list(target_x), _resample_to_grid(x_sorted, y_sorted, target_x, algorithm))

    if mode == "spacing":
        spacing_mode = str(options.get("spacing_mode", "") or "").strip().lower()
        if not spacing_mode:
            spacing_mode = "coord" if ("step" in options or "spacing" in options) else "point"
        if spacing_mode == "coord":
            spacing = float(options.get("step", options.get("spacing", 0.0)) or 0.0)
            if spacing <= 0:
                raise ValueError("坐标间距必须大于 0")
            nx, ny = _resample_uniform_spacing(x_sorted, y_sorted, spacing)
            return line_from_xy(nx, ny)
        nx, ny = _resample_uniform(x_sorted, y_sorted, max(2, int(options.get("n", 200) or 200)))
        return line_from_xy(nx, ny)

    nx, ny = _resample_uniform(x_sorted, y_sorted, max(2, int(options.get("n", 200) or 200)))
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
