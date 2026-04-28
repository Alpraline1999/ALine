from __future__ import annotations

import math
from typing import Any, Dict, List

from core.extension_api import AnalysisExtension
from extensions.processing.extension_tools import line_xy, primary_line


VERSION = "0.1.0"


def compute_statistics(xs: List[float], ys: List[float]) -> Dict[str, Any]:
    def _stats(vals: List[float], label: str) -> dict:
        n = len(vals)
        if n == 0:
            return {}
        try:
            import numpy as np

            a = np.asarray(vals, dtype=float)
            return {
                f"{label}_n": n,
                f"{label}_min": float(a.min()),
                f"{label}_max": float(a.max()),
                f"{label}_mean": float(a.mean()),
                f"{label}_std": float(a.std()),
                f"{label}_median": float(np.median(a)),
                f"{label}_p25": float(np.percentile(a, 25)),
                f"{label}_p75": float(np.percentile(a, 75)),
            }
        except ImportError:
            mn = min(vals)
            mx = max(vals)
            mean = sum(vals) / n
            std = math.sqrt(sum((value - mean) ** 2 for value in vals) / n)
            sv = sorted(vals)
            median = sv[n // 2] if n % 2 == 1 else (sv[n // 2 - 1] + sv[n // 2]) / 2
            p25 = sv[int(0.25 * n)]
            p75 = sv[int(0.75 * n)]
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
    del params
    if not lines:
        raise ValueError("statistics 需要至少一条输入数据")
    xs, ys = line_xy(primary_line(lines))
    result = compute_statistics(xs, ys)
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
