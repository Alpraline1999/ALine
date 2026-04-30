from __future__ import annotations

"""正式对外的处理扩展工具。

仅 __all__ 中列出的名称视为稳定的扩展工具接口。
扩展实现优先使用 line_from_xy、line_xy、primary_line、align_lines_to_common_x
这组基础工具；单扩展专用算法逻辑应保留在各自扩展文件内。
"""

import math
from typing import Any, Dict, List, Optional, Tuple

from core.line_tools import (
    Line,
    Point,
    XY,
    line_from_xy,
    line_xy,
    normalize_line,
    normalize_lines,
    series_payload_to_line,
    series_payloads_to_lines,
)


BUILTIN_EXTENSION_VERSION = "0.1.0"

__all__ = [
    "BUILTIN_EXTENSION_VERSION",
    "Point",
    "Line",
    "XY",
    "normalize_line",
    "normalize_lines",
    "line_from_xy",
    "line_xy",
    "primary_line",
    "series_payload_to_line",
    "series_payloads_to_lines",
    "align_lines_to_common_x",
    "resolve_sample_rate",
]


def primary_line(lines: Any) -> Line:
    """返回输入曲线列表中的第一条曲线。"""
    normalized = normalize_lines(lines)
    return normalized[0] if normalized else []


def align_lines_to_common_x(
    lines: List[Line],
    params: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Line], List[str]]:
    """将多条曲线对齐到公共 X 网格。

    strict 模式下要求输入 X 已经完全一致；auto 模式下会在重叠区间内自动重采样。
    返回值为 (aligned_lines, warnings)。
    """
    prepared_lines = [_sorted_line(line) for line in normalize_lines(lines)]
    if len(prepared_lines) < 2:
        return prepared_lines, []
    if _lines_share_same_x(prepared_lines):
        return prepared_lines, []

    options = dict(params or {})
    align_mode = str(options.get("align_mode", "auto") or "auto").strip().lower()
    if align_mode == "strict":
        raise ValueError("输入曲线 X 坐标未对齐，需进行坐标间距重采样")

    grid = _build_alignment_grid(prepared_lines, options)
    aligned_lines = []
    for line in prepared_lines:
        xs, ys = line_xy(line)
        aligned_lines.append(line_from_xy(list(grid), [_interp_linear(x_value, xs, ys) for x_value in grid]))

    description = _describe_alignment_mode(options, len(grid))
    warnings = [
        "需进行坐标间距重采样",
        f"输入曲线 X 坐标未对齐，已在重叠区间内按{description}自动重采样。",
    ]
    return aligned_lines, warnings


def resolve_sample_rate(xs: List[float], params: Dict[str, Any]) -> Optional[float]:
    """从参数或 X 采样间距推断采样率。"""
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
    step = _estimate_sample_spacing(xs)
    if step is None or step <= 0:
        return None
    return 1.0 / step


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
        return line_xy(line_from_xy(xs, ys))

    pairs.sort(key=lambda item: item[0])
    unique_x: List[float] = []
    unique_y: List[float] = []
    for x_value, y_value in pairs:
        if unique_x and math.isclose(x_value, unique_x[-1], rel_tol=0.0, abs_tol=1e-12):
            unique_y[-1] = y_value
            continue
        unique_x.append(x_value)
        unique_y.append(y_value)
    return line_xy(line_from_xy(unique_x, unique_y))


def _estimate_sample_spacing(xs: List[float]) -> Optional[float]:
    x_sorted, _ = _sorted_unique_xy(xs, xs)
    if len(x_sorted) < 2:
        return None
    diffs = [x_sorted[index + 1] - x_sorted[index] for index in range(len(x_sorted) - 1)]
    diffs = [abs(diff) for diff in diffs if diff and math.isfinite(diff)]
    if not diffs:
        return None
    diffs.sort()
    return diffs[len(diffs) // 2]


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


def _sorted_line(line: Line) -> Line:
    xs, ys = line_xy(line)
    sorted_xs, sorted_ys = _sorted_unique_xy(xs, ys)
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


def _build_alignment_grid(lines: List[Line], params: Dict[str, Any]) -> List[float]:
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
            step = _recommended_alignment_spacing(lines)
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


def _recommended_alignment_spacing(lines: List[Line]) -> float:
    spacings = [
        spacing
        for line in lines
        for spacing in [_estimate_sample_spacing(line_xy(line)[0])]
        if spacing is not None and spacing > 0
    ]
    return min(spacings) if spacings else 0.0


def _describe_alignment_mode(params: Dict[str, Any], point_count: int) -> str:
    resample_mode = str(params.get("resample_mode", params.get("mode", "count")) or "count").strip().lower()
    if resample_mode == "spacing":
        step = float(params.get("step", params.get("spacing", 0.0)) or 0.0)
        return f"固定间距({step:g})"
    return f"固定点数({point_count}点)"
