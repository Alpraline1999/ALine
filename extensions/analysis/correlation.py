from __future__ import annotations

import math
from typing import Any, Dict, List

from core.extension_api import AnalysisExtension, ExtensionConfigField


VERSION = "0.1.0"


def compute_correlation(ys1: List[float], ys2: List[float], method: str = "pearson") -> Dict[str, Any]:
    n = min(len(ys1), len(ys2))
    if n < 3:
        raise ValueError("至少需要 3 个数据点")
    y1 = ys1[:n]
    y2 = ys2[:n]
    if method == "spearman":
        try:
            from scipy.stats import spearmanr

            r, p = spearmanr(y1, y2)
            return {"method": "spearman", "r": float(r), "p_value": float(p)}
        except ImportError:
            pass
    try:
        from scipy.stats import pearsonr

        r, p = pearsonr(y1, y2)
        return {"method": "pearson", "r": float(r), "p_value": float(p)}
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


def _handler(inputs, params):
    if len(inputs) < 2:
        raise ValueError("correlation 需要两条输入数据")
    first = dict(inputs[0] or {})
    second = dict(inputs[1] or {})
    result = compute_correlation(
        list(first.get("y", []) or []),
        list(second.get("y", []) or []),
        str(params.get("method", "pearson") or "pearson"),
    )
    result["analysis_type"] = "correlation"
    result["name1"] = first.get("name", "")
    result["name2"] = second.get("name", "")
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
