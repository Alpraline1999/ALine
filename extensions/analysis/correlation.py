from __future__ import annotations

import math
from typing import Any, Dict, List

from core.extension_api import AnalysisExtension, ExtensionConfigField
from extensions.processing.extension_tools import line_xy, normalize_lines


VERSION = "0.1.0"


def _result_pair(result: Any) -> tuple[float, float]:
    statistic = getattr(result, "statistic", None)
    p_value = getattr(result, "pvalue", None)
    if statistic is None or p_value is None:
        statistic, p_value = result
    return float(statistic), float(p_value)


def compute_correlation(ys1: List[float], ys2: List[float], method: str = "pearson") -> Dict[str, Any]:
    n = min(len(ys1), len(ys2))
    if n < 3:
        raise ValueError("至少需要 3 个数据点")
    y1 = ys1[:n]
    y2 = ys2[:n]
    if method == "spearman":
        try:
            from scipy.stats import spearmanr

            statistic, p_value = _result_pair(spearmanr(y1, y2))
            return {"method": "spearman", "r": float(statistic), "p_value": float(p_value)}
        except ImportError:
            pass
    try:
        from scipy.stats import pearsonr

        statistic, p_value = _result_pair(pearsonr(y1, y2))
        return {"method": "pearson", "r": float(statistic), "p_value": float(p_value)}
    except ImportError:
        try:
            import numpy as np

            a1 = np.asarray(y1, dtype=float)
            a2 = np.asarray(y2, dtype=float)
            a1c = a1 - a1.mean()
            a2c = a2 - a2.mean()
            denom = (np.linalg.norm(a1c) * np.linalg.norm(a2c)) or 1.0
            r = float(np.dot(a1c, a2c) / denom)
        except ImportError:
            mean1 = sum(y1) / n
            mean2 = sum(y2) / n
            num = sum((a - mean1) * (b - mean2) for a, b in zip(y1, y2))
            d1 = math.sqrt(sum((a - mean1) ** 2 for a in y1))
            d2 = math.sqrt(sum((b - mean2) ** 2 for b in y2))
            r = num / (d1 * d2 or 1.0)
        return {"method": "pearson", "r": r, "p_value": None}


def _handler(lines, params):
    normalized_lines = normalize_lines(lines)
    if len(normalized_lines) < 2:
        raise ValueError("correlation 需要两条输入数据")
    first = normalized_lines[0]
    second = normalized_lines[1]
    _x1, y1 = line_xy(first)
    _x2, y2 = line_xy(second)
    result = compute_correlation(
        y1,
        y2,
        str(params.get("method", "pearson") or "pearson"),
    )
    result["analysis_type"] = "correlation"
    return result


def register_extensions(registry) -> None:
    registry.register_analysis(
        AnalysisExtension(
            type="correlation",
            name="相关性",
            handler=_handler,
            description="计算两条曲线之间的 Pearson 或 Spearman 相关性。",
            version=VERSION,
            lines_number=(2, 2),
            settings=True,
            source_kind="builtin",
            config_fields=[
                ExtensionConfigField(
                    key="method",
                    label="相关性方法",
                    field_type="selective",
                    default="pearson",
                    choices=("pearson", "spearman"),
                )
            ],
        )
    )
