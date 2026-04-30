from __future__ import annotations

"""Core 级曲线/线工具。

这些函数是扩展协议的基础转换层，供 core 和扩展共享使用。
"""

import math
from typing import Any, Dict, List, Optional, Tuple

from core.curve_data import (
    CurveBuffer,
    SeriesArrayView,
    curve_buffer_to_line,
    curve_buffer_to_views,
    line_to_curve_buffer,
    series_payload_to_curve_buffer,
    series_payloads_to_curve_batch,
)

Point = List[float]
Line = List[Point]
XY = Tuple[SeriesArrayView, SeriesArrayView]

__all__ = [
    "CurveBuffer",
    "SeriesArrayView",
    "Point",
    "Line",
    "XY",
    "normalize_line",
    "normalize_lines",
    "line_from_xy",
    "line_xy",
    "primary_line",
    "sorted_unique_xy",
    "estimate_sample_spacing",
    "interp_linear",
    "resample_uniform",
    "resample_uniform_spacing",
    "nearest_value",
    "x_values_equal",
    "resample_to_grid",
    "build_alignment_grid",
    "recommended_alignment_spacing",
    "describe_alignment_mode",
    "resolve_sample_rate",
    "align_lines_to_common_x",
    "line_to_curve_buffer",
    "curve_buffer_to_line",
    "curve_buffer_to_views",
    "series_payload_to_line",
    "series_payloads_to_lines",
    "series_payload_to_curve_buffer",
    "series_payloads_to_curve_batch",
]


def _normalize_point(raw: Any, index: int) -> Point:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError(f"line 第 {index + 1} 个点必须是 [x, y]")
    try:
        x_value = float(raw[0])
        y_value = float(raw[1])
    except (TypeError, ValueError):
        raise ValueError(f"line 第 {index + 1} 个点包含非数值坐标") from None
    if not math.isfinite(x_value) or not math.isfinite(y_value):
        raise ValueError(f"line 第 {index + 1} 个点包含无效坐标")
    return [x_value, y_value]


def normalize_line(raw: Any) -> Line:
    if not isinstance(raw, (list, tuple)):
        raise ValueError("line 必须是 point-list，即 [[x, y], ...]")
    return [_normalize_point(point, index) for index, point in enumerate(list(raw))]


def normalize_lines(raw: Any) -> List[Line]:
    if raw in (None, "", [], ()):  # type: ignore[comparison-overlap]
        return []
    return [normalize_line(item) for item in list(raw)]


def line_from_xy(xs: List[float], ys: List[float]) -> Line:
    return CurveBuffer.from_xy(xs, ys).to_line()


def line_xy(line: Any) -> XY:
    return curve_buffer_to_views(line_to_curve_buffer(line))


def series_payload_to_line(item: Any) -> Line:
    return curve_buffer_to_line(series_payload_to_curve_buffer(item))


def series_payloads_to_lines(raw: Any) -> List[Line]:
    return [buffer.to_line() for buffer in series_payloads_to_curve_batch(raw)]


def primary_line(lines: Any) -> Line:
    normalized = normalize_lines(lines)
    return normalized[0] if normalized else []


def sorted_unique_xy(xs: List[float], ys: List[float]) -> XY:
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


def estimate_sample_spacing(xs: List[float]) -> Optional[float]:
    x_sorted, _ = sorted_unique_xy(xs, xs)
    if len(x_sorted) < 2:
        return None
    diffs = [x_sorted[index + 1] - x_sorted[index] for index in range(len(x_sorted) - 1)]
    diffs = [abs(diff) for diff in diffs if diff and math.isfinite(diff)]
    if not diffs:
        return None
    diffs.sort()
    return diffs[len(diffs) // 2]


def interp_linear(x_value: float, xs: List[float], ys: List[float]) -> float:
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


def resample_uniform(xs: List[float], ys: List[float], n_points: int) -> XY:
    if len(xs) < 2 or n_points < 2:
        return list(xs), list(ys)
    x_min, x_max = xs[0], xs[-1]
    if math.isclose(x_min, x_max, rel_tol=0.0, abs_tol=1e-12):
        return list(xs), list(ys)
    target_x = [x_min + index * (x_max - x_min) / (n_points - 1) for index in range(n_points)]
    return target_x, [interp_linear(x_value, xs, ys) for x_value in target_x]


def resample_uniform_spacing(xs: List[float], ys: List[float], spacing: float) -> XY:
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
    return target_x, [interp_linear(x_value, xs, ys) for x_value in target_x]


def nearest_value(x_value: float, xs: List[float], ys: List[float]) -> float:
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


def x_values_equal(left_values: List[float], right_values: List[float]) -> bool:
    if len(left_values) != len(right_values):
        return False
    for left, right in zip(left_values, right_values):
        if not math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12):
            return False
    return True


def resample_to_grid(xs: List[float], ys: List[float], target_x: List[float], algorithm: str) -> List[float]:
    mode = str(algorithm or "linear").strip().lower()
    if mode == "nearest":
        return [nearest_value(float(value), xs, ys) for value in target_x]
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
                    result.append(interp_linear(float(fallback_x), xs, ys))
                else:
                    result.append(raw_value)
            return result
        except Exception:
            pass
    return [interp_linear(float(value), xs, ys) for value in target_x]


def resolve_sample_rate(xs: List[float], params: Dict[str, Any]) -> Optional[float]:
    raw_sample_rate = params.get("sampling_rate")
    if raw_sample_rate in (None, ""):
        sample_rate = 0.0
    else:
        try:
            sample_rate = float(raw_sample_rate)
        except (TypeError, ValueError):
            sample_rate = 0.0
    if sample_rate > 0:
        return sample_rate
    step = estimate_sample_spacing(xs)
    if step is None or step <= 0:
        return None
    return 1.0 / step


def _sorted_line(line: Line) -> Line:
    xs, ys = line_xy(line)
    sorted_xs, sorted_ys = sorted_unique_xy(xs, ys)
    return line_from_xy(sorted_xs, sorted_ys)


def _lines_share_same_x(lines: List[Line]) -> bool:
    if len(lines) < 2:
        return True
    base_x, _base_y = line_xy(lines[0])
    for line in lines[1:]:
        current_x, _current_y = line_xy(line)
        if len(current_x) != len(base_x):
            return False
        for left, right in zip(base_x, current_x):
            if not math.isclose(left, right, rel_tol=0.0, abs_tol=1e-9):
                return False
    return True


def build_alignment_grid(lines: List[Line], params: Dict[str, Any]) -> List[float]:
    x_values = [line_xy(line)[0] for line in lines]
    starts = [float(xs[0]) for xs in x_values if len(xs) >= 2]
    ends = [float(xs[-1]) for xs in x_values if len(xs) >= 2]
    if not starts or not ends:
        raise ValueError("自动对齐至少需要每条曲线包含两个有效采样点")
    x_start = max(starts)
    x_end = min(ends)
    if x_end - x_start <= 1e-12:
        raise ValueError("输入曲线没有足够的重叠区间，无法执行自动对齐")

    resample_mode = str(params.get("resample_mode", params.get("mode", "count")) or "count").strip().lower()
    if resample_mode == "spacing":
        step = float(params.get("step", params.get("spacing", 0.0)) or 0.0)
        if step <= 0:
            step = recommended_alignment_spacing(lines)
        if step <= 0:
            raise ValueError("无法推断有效的自动对齐重采样间距")
        grid = [x_start]
        next_x = x_start + step
        while next_x < x_end - 1e-12:
            grid.append(next_x)
            next_x += step
        if not math.isclose(grid[-1], x_end, rel_tol=0.0, abs_tol=1e-12):
            grid.append(x_end)
        return grid

    n_points = int(params.get("n", 0) or 0)
    if n_points < 2:
        n_points = max(len(xs) for xs in x_values)
    n_points = max(2, n_points)
    return [x_start + index * (x_end - x_start) / (n_points - 1) for index in range(n_points)]


def recommended_alignment_spacing(lines: List[Line]) -> float:
    spacings = [
        spacing
        for line in lines
        for spacing in [estimate_sample_spacing(line_xy(line)[0])]
        if spacing is not None and spacing > 0
    ]
    return min(spacings) if spacings else 0.0


def describe_alignment_mode(params: Dict[str, Any], point_count: int) -> str:
    resample_mode = str(params.get("resample_mode", params.get("mode", "count")) or "count").strip().lower()
    if resample_mode == "spacing":
        step = float(params.get("step", params.get("spacing", 0.0)) or 0.0)
        return f"固定间距({step:g})"
    return f"固定点数({point_count}点)"


def align_lines_to_common_x(
    lines: List[Line],
    params: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Line], List[str]]:
    prepared_lines = [_sorted_line(line) for line in normalize_lines(lines)]
    if len(prepared_lines) < 2:
        return prepared_lines, []
    if _lines_share_same_x(prepared_lines):
        return prepared_lines, []

    options = dict(params or {})
    align_mode = str(options.get("align_mode", "auto") or "auto").strip().lower()
    if align_mode == "strict":
        raise ValueError("输入曲线 X 坐标未对齐，需进行坐标间距重采样")

    grid = build_alignment_grid(prepared_lines, options)
    aligned_lines = []
    for line in prepared_lines:
        xs, ys = line_xy(line)
        aligned_lines.append(line_from_xy(list(grid), [interp_linear(x_value, xs, ys) for x_value in grid]))

    description = describe_alignment_mode(options, len(grid))
    warnings = [
        "需进行坐标间距重采样",
        f"输入曲线 X 坐标未对齐，已在重叠区间内按{description}自动重采样。",
    ]
    return aligned_lines, warnings
