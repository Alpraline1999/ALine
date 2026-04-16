"""
曲线平滑与重采样模块

直接迁移自 PyLine core/smoother.py，无外部依赖（纯 Python 实现）。
"""
from __future__ import annotations

import math
from typing import List, Tuple


def smooth_moving_average(
    x: List[float],
    y: List[float],
    window: int = 3,
) -> Tuple[List[float], List[float]]:
    """移动平均平滑。

    Args:
        x, y: 输入坐标列表（长度相同，已按 x 排序）。
        window: 窗口大小（强制为奇数且 >= 3）。
    Returns:
        (x_smooth, y_smooth)
    """
    if len(x) < 2:
        return list(x), list(y)
    window = max(3, window | 1)
    half = window // 2
    n = len(y)
    y_smooth = []
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        y_smooth.append(sum(y[lo:hi]) / (hi - lo))
    return list(x), y_smooth


def smooth_savgol(
    x: List[float],
    y: List[float],
    window: int = 5,
    poly: int = 2,
) -> Tuple[List[float], List[float]]:
    """Savitzky-Golay 平滑（纯 Python 实现，无 scipy 依赖）。

    Args:
        x, y: 输入列表。
        window: 窗口大小（奇数，>= poly+1）。
        poly: 多项式阶数。
    Returns:
        (x_smooth, y_smooth)
    """
    if len(x) < window:
        return smooth_moving_average(x, y, window=max(3, len(x) | 1))
    window = max(poly + 1, window | 1)
    half = window // 2
    coeffs = _savgol_coeffs(window, poly)
    n = len(y)
    y_smooth = []
    for i in range(n):
        sub = []
        for j in range(i - half, i + half + 1):
            if 0 <= j < n:
                sub.append(y[j])
            elif j < 0:
                sub.append(y[0])
            else:
                sub.append(y[-1])
        y_smooth.append(sum(c * v for c, v in zip(coeffs, sub)))
    return list(x), y_smooth


def resample_uniform(
    x: List[float],
    y: List[float],
    n_points: int,
) -> Tuple[List[float], List[float]]:
    """均匀间隔重采样（线性插值）。

    Args:
        x, y: 输入列表（已按 x 排序）。
        n_points: 重采样点数。
    Returns:
        (x_new, y_new)
    """
    if len(x) < 2 or n_points < 2:
        return list(x), list(y)
    x_min, x_max = x[0], x[-1]
    if x_min == x_max:
        return list(x), list(y)
    x_new = [x_min + i * (x_max - x_min) / (n_points - 1) for i in range(n_points)]
    y_new = [_interp(xv, x, y) for xv in x_new]
    return x_new, y_new


# ── 内部辅助 ────────────────────────────────────────────────

def _savgol_coeffs(window: int, poly: int) -> List[float]:
    half = window // 2
    J = [[float(i ** k) for k in range(poly + 1)] for i in range(-half, half + 1)]
    JT = _transpose(J)
    JTJ = _matmul(JT, J)
    JTJ_inv = _mat_inv(JTJ)
    pinv = _matmul(JTJ_inv, JT)
    return pinv[0]


def _transpose(m: List[List[float]]) -> List[List[float]]:
    return [[m[r][c] for r in range(len(m))] for c in range(len(m[0]))]


def _matmul(a: List[List[float]], b: List[List[float]]) -> List[List[float]]:
    ra, ca = len(a), len(a[0])
    cb = len(b[0])
    result = [[0.0] * cb for _ in range(ra)]
    for i in range(ra):
        for j in range(cb):
            for k in range(ca):
                result[i][j] += a[i][k] * b[k][j]
    return result


def _mat_inv(m: List[List[float]]) -> List[List[float]]:
    n = len(m)
    aug = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(m)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        aug[col], aug[pivot] = aug[pivot], aug[col]
        div = aug[col][col]
        if abs(div) < 1e-12:
            raise ValueError("矩阵奇异，无法求逆")
        aug[col] = [v / div for v in aug[col]]
        for row in range(n):
            if row != col:
                factor = aug[row][col]
                aug[row] = [aug[row][j] - factor * aug[col][j] for j in range(2 * n)]
    return [row[n:] for row in aug]


def _interp(x_val: float, x: List[float], y: List[float]) -> float:
    if x_val <= x[0]:
        return y[0]
    if x_val >= x[-1]:
        return y[-1]
    lo, hi = 0, len(x) - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if x[mid] <= x_val:
            lo = mid
        else:
            hi = mid
    t = (x_val - x[lo]) / (x[hi] - x[lo])
    return y[lo] + t * (y[hi] - y[lo])
