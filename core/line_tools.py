from __future__ import annotations

"""Core 级曲线/线工具。

这些函数是扩展协议的基础转换层，供 core 和扩展共享使用。
"""

import math
from typing import Any, List, Optional, Tuple

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
