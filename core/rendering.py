from __future__ import annotations

"""渲染热路径的轻量辅助函数。

当前只提供低风险的曲线点降采样策略，用于图表预览等大曲线场景。
它不改变数据源本身，也不负责坐标轴裁剪或格式化。
"""

from dataclasses import dataclass
from math import ceil
from typing import Any, Iterable, Sequence


@dataclass(frozen=True, slots=True)
class RenderDecimationPolicy:
    """渲染降采样策略。"""

    max_points: int = 2000
    preserve_endpoints: bool = True

    def normalized(self) -> "RenderDecimationPolicy":
        max_points = int(self.max_points or 0)
        if max_points < 2:
            max_points = 2
        return RenderDecimationPolicy(max_points=max_points, preserve_endpoints=bool(self.preserve_endpoints))


def build_render_decimation_indices(length: int, policy: RenderDecimationPolicy | None = None) -> list[int]:
    policy = (policy or RenderDecimationPolicy()).normalized()
    if length <= 0:
        return []
    if length <= policy.max_points:
        return list(range(length))

    step = max(2, ceil(length / policy.max_points))
    indices = list(range(0, length, step))
    if policy.preserve_endpoints and indices[-1] != length - 1:
        indices.append(length - 1)
    return indices


def decimate_xy_for_rendering(
    xs: Sequence[Any] | Iterable[Any],
    ys: Sequence[Any] | Iterable[Any],
    policy: RenderDecimationPolicy | None = None,
) -> tuple[list[Any], list[Any], list[int]]:
    x_values = list(xs)
    y_values = list(ys)
    if len(x_values) != len(y_values):
        limit = min(len(x_values), len(y_values))
        x_values = x_values[:limit]
        y_values = y_values[:limit]

    indices = build_render_decimation_indices(len(x_values), policy)
    if len(indices) == len(x_values):
        return x_values, y_values, indices

    return [x_values[index] for index in indices], [y_values[index] for index in indices], indices

