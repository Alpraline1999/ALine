"""
坐标校准模块 — 像素坐标 → 真实坐标

从 PyLine core/project_manager.py 提取的坐标变换逻辑，
作为纯函数模块独立于 ProjectManager，便于在其他模块复用。

支持三种坐标类型：
  - linear: 线性坐标（默认）
  - log:    对数坐标
  - polar:  极坐标（2点校准）
"""
from __future__ import annotations

import math
from typing import Tuple

from models.schemas import CalibrationData


def compute_actual_coords(
    calib: CalibrationData,
    px: float,
    py: float,
) -> Tuple[float, float]:
    """将像素坐标 (px, py) 转换为真实坐标。

    根据 calib.coord_type 分发到对应的坐标变换函数。

    Returns:
        (x_actual, y_actual) 或极坐标 (r_actual, theta_actual)。
    """
    if calib.coord_type == "polar":
        return _compute_polar(calib, px, py)
    elif calib.coord_type == "log":
        return _compute_log(calib, px, py)
    else:
        return _compute_linear(calib, px, py)


# ── 线性坐标 ────────────────────────────────────────────────

def _compute_linear(calib: CalibrationData, px: float, py: float) -> Tuple[float, float]:
    """线性坐标转换（投影法）。"""
    x_actual = _project_to_axis(
        px, py,
        calib.x_start, calib.x_end,
        calib.x_range[0], calib.x_range[1],
        log=False,
    )
    y_actual = _project_to_axis(
        px, py,
        calib.y_start, calib.y_end,
        calib.y_range[0], calib.y_range[1],
        log=False,
    )
    return x_actual, y_actual


# ── 对数坐标 ────────────────────────────────────────────────

def _compute_log(calib: CalibrationData, px: float, py: float) -> Tuple[float, float]:
    """对数坐标转换。"""
    x_actual = _project_to_axis(
        px, py,
        calib.x_start, calib.x_end,
        calib.x_range[0], calib.x_range[1],
        log=True,
    )
    y_actual = _project_to_axis(
        px, py,
        calib.y_start, calib.y_end,
        calib.y_range[0], calib.y_range[1],
        log=True,
    )
    return x_actual, y_actual


# ── 极坐标 ───────────────────────────────────────────────────

def _compute_polar(calib: CalibrationData, px: float, py: float) -> Tuple[float, float]:
    """极坐标转换（2点校准）。

    校准参数：
        x_start: 极点像素坐标
        x_end:   参考点A像素坐标（对应实际角度 angle_A、极径 radius_A）

    算法：
        P 的像素半径 / A 的像素半径 = actual_r / radius_A
        actual_theta = angle_A + (direction_A - theta_P)  归一化到 [0, 360)
    """
    origin_x, origin_y = calib.x_start
    point_a_x, point_a_y = calib.x_end

    vx = px - origin_x
    vy = py - origin_y
    pixel_r = math.sqrt(vx * vx + vy * vy)
    theta_p = math.atan2(vy, vx) * 180.0 / math.pi

    da_x = point_a_x - origin_x
    da_y = point_a_y - origin_y
    direction_a = math.atan2(da_y, da_x) * 180.0 / math.pi
    pixel_scale = math.sqrt(da_x * da_x + da_y * da_y)

    r_actual = (pixel_r / pixel_scale) * calib.radius_A if pixel_scale > 0 else 0.0
    theta_actual = calib.angle_A + direction_a - theta_p
    theta_actual %= 360.0

    return r_actual, theta_actual


# ── 内部辅助 ─────────────────────────────────────────────────

def _project_to_axis(
    px: float,
    py: float,
    start: tuple,
    end: tuple,
    val_min: float,
    val_max: float,
    log: bool,
) -> float:
    """将点 (px, py) 投影到轴线段上，返回插值后的真实值。"""
    dx = end[0] - start[0]
    dy = end[1] - start[1]

    if abs(dx) >= abs(dy):
        t = (px - start[0]) / dx if dx != 0 else 0.0
    else:
        t = (py - start[1]) / dy if dy != 0 else 0.0

    if log:
        log_min = math.log10(max(val_min, 1e-300))
        log_max = math.log10(max(val_max, 1e-300))
        return math.pow(10.0, log_min + t * (log_max - log_min))
    else:
        return val_min + t * (val_max - val_min)
