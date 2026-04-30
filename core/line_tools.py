from __future__ import annotations

"""Core 级曲线/线工具。

这些函数是扩展协议的基础转换层，供 core 和扩展共享使用。
"""

import math
from typing import Any, List, Optional, Tuple

Point = List[float]
Line = List[Point]
XY = Tuple[List[float], List[float]]

__all__ = [
    "Point",
    "Line",
    "XY",
    "normalize_line",
    "normalize_lines",
    "line_from_xy",
    "line_xy",
    "series_payload_to_line",
    "series_payloads_to_lines",
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
    x_values = list(xs or [])
    y_values = list(ys or [])
    if len(x_values) != len(y_values):
        raise ValueError("x_list 与 y_list 长度必须一致，无法转换为 line")
    return normalize_line([[x_value, y_value] for x_value, y_value in zip(x_values, y_values)])


def line_xy(line: Any) -> XY:
    normalized = normalize_line(line)
    return [point[0] for point in normalized], [point[1] for point in normalized]


def series_payload_to_line(item: Any) -> Line:
    if isinstance(item, dict):
        return line_from_xy(list(item.get("x", []) or []), list(item.get("y", []) or []))
    return line_from_xy(list(getattr(item, "x", []) or []), list(getattr(item, "y", []) or []))


def series_payloads_to_lines(raw: Any) -> List[Line]:
    return [series_payload_to_line(item) for item in list(raw or [])]
