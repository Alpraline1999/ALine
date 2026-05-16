from __future__ import annotations

import math
from typing import Any, Dict, List

from core.extension_api import AnalysisExtension
from extensions.processing.extension_tools import line_xy, primary_line


VERSION = "0.1.0"


def _linear_percentile(sorted_vals: List[float], percentile: float) -> float:
    """Linear interpolation percentile (numpy default method)."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_vals[0]
    idx = percentile / 100.0 * (n - 1)
    lo = int(math.floor(idx))
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


def compute_statistics(xs: List[float], ys: List[float]) -> Dict[str, Any]:
    def _stats(vals: List[float], label: str) -> dict:
        n = len(vals)
        if n == 0:
            return {}
        try:
            import numpy as np

            a = np.asarray(vals, dtype=float)
            mean = float(a.mean())
            std = float(a.std())
            # Skewness and kurtosis using numpy primitives
            centered = a - mean
            skew = float(np.mean(centered ** 3) / (std ** 3)) if std > 1e-12 else 0.0
            kurt = float(np.mean(centered ** 4) / (std ** 4)) - 3.0 if std > 1e-12 else 0.0
            return {
                f"{label}_n": n,
                f"{label}_min": float(a.min()),
                f"{label}_max": float(a.max()),
                f"{label}_mean": mean,
                f"{label}_std": std,
                f"{label}_median": float(np.median(a)),
                f"{label}_p25": float(np.percentile(a, 25)),
                f"{label}_p75": float(np.percentile(a, 75)),
                f"{label}_skewness": skew,
                f"{label}_kurtosis": kurt,
            }
        except ImportError:
            mn = min(vals)
            mx = max(vals)
            mean = sum(vals) / n
            std = math.sqrt(sum((value - mean) ** 2 for value in vals) / n)
            sv = sorted(vals)
            median = _linear_percentile(sv, 50)
            p25 = _linear_percentile(sv, 25)
            p75 = _linear_percentile(sv, 75)
            return {
                f"{label}_n": n,
                f"{label}_min": mn,
                f"{label}_max": mx,
                f"{label}_mean": mean,
                f"{label}_std": std,
                f"{label}_median": median,
                f"{label}_p25": p25,
                f"{label}_p75": p75,
            }

    result = {"n": min(len(xs), len(ys))}
    result.update(_stats(xs, "x"))
    result.update(_stats(ys, "y"))
    return result


def _handler(lines, params):
    if not lines:
        raise ValueError("statistics 需要至少一条输入数据")
    xs, ys = line_xy(primary_line(lines))
    result = compute_statistics(xs, ys)
    n = result.get("n", 0)
    summary = [
        {"label": "X 最小值", "value": result.get("x_min", "")},
        {"label": "X 最大值", "value": result.get("x_max", "")},
        {"label": "Y 最小值", "value": result.get("y_min", "")},
        {"label": "Y 最大值", "value": result.get("y_max", "")},
        {"label": "Y 均值", "value": result.get("y_mean", "")},
        {"label": "Y 标准差", "value": result.get("y_std", "")},
    ]
    y_skew = result.get("y_skewness")
    y_kurt = result.get("y_kurtosis")
    if y_skew is not None:
        summary.append({"label": "Y 偏度", "value": f"{y_skew:.4f}"})
    if y_kurt is not None:
        summary.append({"label": "Y 峰度", "value": f"{y_kurt:.4f}"})
    result["summary_items"] = summary
    result["analysis_type"] = "statistics"
    return result


def register_extensions(registry) -> None:
    registry.register_analysis(
        AnalysisExtension(
            type="statistics",
            name="统计分析",
            handler=_handler,
            description="计算当前曲线的常用统计量。",
            version=VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
        )
    )
