from __future__ import annotations

import math
from typing import Any, Dict, List

from core.extension_api import AnalysisExtension


VERSION = "0.1.0"


def compute_error_metrics(xs1: List[float], ys1: List[float], xs2: List[float], ys2: List[float]) -> Dict[str, Any]:
    n = min(len(xs1), len(ys1), len(xs2), len(ys2))
    if n < 2:
        raise ValueError("误差比较至少需要 2 个对齐数据点")
    xs = list(xs1[:n])
    ref = list(ys1[:n])
    cmp = list(ys2[:n])
    error_y = [left - right for left, right in zip(ref, cmp)]
    abs_error = [abs(value) for value in error_y]
    mae = sum(abs_error) / n
    rmse = math.sqrt(sum(value * value for value in error_y) / n)
    mean_error = sum(error_y) / n
    max_abs_error = max(abs_error)
    relative_errors = [abs(error / base) for error, base in zip(error_y, ref) if base not in (0, 0.0)]
    relative_mae = (sum(relative_errors) / len(relative_errors)) if relative_errors else None
    return {
        "analysis_type": "error_compare",
        "n": n,
        "error_x": xs,
        "error_y": error_y,
        "mae": mae,
        "rmse": rmse,
        "mean_error": mean_error,
        "max_abs_error": max_abs_error,
        "relative_mae": relative_mae,
    }


def _handler(inputs, params):
    del params
    if len(inputs) < 2:
        raise ValueError("error_compare 需要两条输入数据")
    first = dict(inputs[0] or {})
    second = dict(inputs[1] or {})
    result = compute_error_metrics(
        list(first.get("x", []) or []),
        list(first.get("y", []) or []),
        list(second.get("x", []) or []),
        list(second.get("y", []) or []),
    )
    result["analysis_type"] = "error_compare"
    result["name1"] = first.get("name", "")
    result["name2"] = second.get("name", "")
    return result


def register_extensions(registry) -> None:
    registry.register_analysis(
        AnalysisExtension(
            type="error_compare",
            name="误差对比",
            handler=_handler,
            description="比较两条曲线的误差指标并输出误差曲线。",
            version=VERSION,
            lines_number=(2, 2),
            settings=True,
            source_kind="builtin",
        )
    )
