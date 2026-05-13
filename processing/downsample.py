"""LTTB 降采样算法 — 在保持视觉形状的前提下减少渲染点数。"""
from __future__ import annotations

from typing import Tuple

import numpy as np
from numpy import ndarray


def downsample_lttb(
    x: ndarray, y: ndarray, max_points: int = 10000
) -> Tuple[ndarray, ndarray]:
    """LTTB (Largest Triangle Three Buckets) 降采样。

    在保持视觉形状的前提下将数据点减少到 max_points 个。
    算法复杂度 O(n)，适合实时渲染。

    Args:
        x, y: 输入数据（已按 x 排序）。
        max_points: 目标点数。

    Returns:
        (x_down, y_down) 降采样后的数据。

    Reference:
        Sveinn Steinarsson. 2013.
        "Downsampling Time Series for Visual Representation."
    """
    n = len(x)
    if n <= max_points:
        return x, y

    # Bucket size
    bucket_size = (n - 2) / (max_points - 2)

    # Result indices (first and last always preserved)
    idxs = [0]

    a = 0
    for i in range(1, max_points - 1):
        # Current bucket range
        bucket_start = int(round((i - 1) * bucket_size) + 1)
        bucket_end = int(round(i * bucket_size) + 1)

        # Average point in next bucket
        avg_x = np.mean(x[bucket_start:bucket_end])
        avg_y = np.mean(y[bucket_start:bucket_end])

        # Find point in current bucket maximizing triangle area
        max_area = -1.0
        max_idx = bucket_start

        for j in range(bucket_start, bucket_end):
            area = abs(
                (x[a] - x[j]) * (y[min(bucket_end, n - 1)] - y[a])
                - (x[a] - x[min(bucket_end, n - 1)]) * (y[a] - y[j])
            )
            if area > max_area:
                max_area = area
                max_idx = j

        idxs.append(max_idx)
        a = max_idx

    idxs.append(n - 1)
    return x[idxs], y[idxs]


def should_downsample(n_points: int, max_points: int = 10000) -> bool:
    """判断是否需要降采样。"""
    return n_points > max_points
