"""Analysis extension shared utilities — imported by analysis extensions."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


def _pearson(values_a: List[float], values_b: List[float]) -> float:
    """Pure-Python Pearson correlation coefficient."""
    count = min(len(values_a), len(values_b))
    if count < 2:
        return 0.0
    trimmed_a = list(values_a[:count])
    trimmed_b = list(values_b[:count])
    mean_a = sum(trimmed_a) / count
    mean_b = sum(trimmed_b) / count
    covariance = sum((left - mean_a) * (right - mean_b) for left, right in zip(trimmed_a, trimmed_b))
    std_a = math.sqrt(sum((value - mean_a) ** 2 for value in trimmed_a))
    std_b = math.sqrt(sum((value - mean_b) ** 2 for value in trimmed_b))
    if std_a <= 1e-12 or std_b <= 1e-12:
        return 0.0
    return covariance / (std_a * std_b)


def _ranks(values: List[float]) -> List[float]:
    """Compute rank order (handles ties)."""
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(indexed):
        end = index
        while end + 1 < len(indexed) and indexed[end + 1][1] == indexed[index][1]:
            end += 1
        rank = (index + end) / 2.0 + 1.0
        for current in range(index, end + 1):
            ranks[indexed[current][0]] = rank
        index = end + 1
    return ranks


def correlation(values_a: List[float], values_b: List[float], method: str = "pearson") -> Dict[str, Any]:
    """Compute Pearson or Spearman correlation with optional p-value.

    Tries scipy for accurate p-value; falls back to pure-Python coefficient only.
    """
    n = min(len(values_a), len(values_b))
    if n < 3:
        raise ValueError("至少需要 3 个数据点")

    if method == "spearman":
        try:
            from scipy.stats import spearmanr

            statistic, p_value = spearmanr(values_a, values_b)
            return {"method": "spearman", "r": float(statistic), "p_value": float(p_value), "n": n}
        except ImportError:
            return {"method": "spearman", "r": _pearson(_ranks(values_a), _ranks(values_b)), "p_value": None, "n": n}

    try:
        from scipy.stats import pearsonr

        statistic, p_value = pearsonr(values_a, values_b)
        return {"method": "pearson", "r": float(statistic), "p_value": float(p_value), "n": n}
    except ImportError:
        return {"method": "pearson", "r": _pearson(values_a, values_b), "p_value": None, "n": n}
