from __future__ import annotations

from typing import Dict, List, Tuple


def build_large_curve_points(count: int = 50_000) -> Tuple[List[float], List[float]]:
    xs = [float(index) * 0.01 for index in range(count)]
    ys = [((index % 200) - 100) * 0.05 for index in range(count)]
    return xs, ys


def build_large_workspace_payload(curve_count: int = 8, points_per_curve: int = 12_500) -> Dict[str, object]:
    series = []
    for curve_index in range(curve_count):
        xs, ys = build_large_curve_points(points_per_curve)
        series.append(
            {
                "id": f"series-{curve_index}",
                "name": f"curve_{curve_index}",
                "x": xs,
                "y": ys,
            }
        )
    return {
        "curve_count": curve_count,
        "points_per_curve": points_per_curve,
        "series": series,
    }
