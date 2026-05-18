from __future__ import annotations

"""正式对外的处理扩展工具。

仅 __all__ 中列出的名称视为稳定的扩展工具接口。
扩展实现优先使用 line_from_xy、line_xy、primary_line、align_lines_to_common_x
这组基础工具；单扩展专用算法逻辑应保留在各自扩展文件内。
"""

from typing import List

import numpy as np

from core.line_tools import (
    Line,
    Point,
    XY,
    align_lines_to_common_x,
    line_from_xy,
    line_xy,
    normalize_line,
    normalize_lines,
    primary_line,
    resolve_sample_rate,
    series_payload_to_line,
    series_payloads_to_lines,
)


BUILTIN_EXTENSION_VERSION = "1.0.0"


def apply_window(size: int, window_name: str) -> np.ndarray:
    """生成窗函数数组。"""
    name = str(window_name or "hann").strip().lower()
    if name == "hamming":
        return np.hamming(size)
    if name == "blackman":
        return np.blackman(size)
    if name in {"rect", "rectangle", "boxcar"}:
        return np.ones(size)
    return np.hanning(size)


def linear_percentile(sorted_vals: List[float], percentile: float) -> float:
    """线性插值百分位数（numpy 默认方法）。"""
    return float(np.percentile(sorted_vals, percentile, method="linear"))


def baseline_correction(
    xs: np.ndarray, ys: np.ndarray, method: str
) -> np.ndarray:
    """对 Y 序列进行基线校正。

    Args:
        xs: X 坐标数组
        ys: Y 值数组
        method: "none" / "constant" / "linear"

    Returns:
        校正后的 Y 数组
    """
    method = str(method or "none").strip().lower()
    if method == "constant" and len(ys) > 0:
        return ys - ys[0]
    if method == "linear" and len(ys) > 1:
        slope = (ys[-1] - ys[0]) / (xs[-1] - xs[0])
        return ys - (ys[0] + slope * (xs - xs[0]))
    return ys


__all__ = [
    "BUILTIN_EXTENSION_VERSION",
    "apply_window",
    "linear_percentile",
    "baseline_correction",
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
