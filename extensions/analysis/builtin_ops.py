from __future__ import annotations

import json
import math
import warnings
from typing import Any, Dict, List, Optional

VERSION = "0.1.0"


def parse_optional_json_list(value):
    if value in (None, "", []):
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        return json.loads(text)
    return value


def fit_curve(
    xs: List[float],
    ys: List[float],
    model: str,
    p0: Optional[List[float]] = None,
) -> Dict[str, Any]:
    try:
        import numpy as np
        from scipy.optimize import OptimizeWarning, curve_fit as _cf
    except ImportError:
        raise ImportError("需要 numpy 和 scipy 才能进行曲线拟合")

    x = np.array(xs, dtype=float)
    y = np.array(ys, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if len(x) < 3:
        raise ValueError("有效数据点不足（需要至少 3 个）")

    fit_funcs = {
        "linear": (lambda x, a, b: a * x + b, ["a", "b"], lambda p: f"y = {p[0]:.4g}·x + {p[1]:.4g}", [1.0, 0.0]),
        "power": (_power_func, ["a", "b"], lambda p: f"y = {p[0]:.4g}·x^{p[1]:.4g}", [1.0, 1.0]),
        "exponential": (lambda x, a, b: a * np.exp(b * x), ["a", "b"], lambda p: f"y = {p[0]:.4g}·e^({p[1]:.4g}·x)", [1.0, 0.01]),
        "gaussian": (
            lambda x, a, mu, sig: a * np.exp(-((x - mu) ** 2) / (2 * sig ** 2)),
            ["a", "μ", "σ"],
            lambda p: f"y = {p[0]:.4g}·exp(-(x-{p[1]:.4g})²/2·{p[2]:.4g}²)",
            [max(y), float(x.mean()), float(x.std()) or 1.0],
        ),
        "poly2": (None, ["a", "b", "c"], lambda p: f"y = {p[0]:.4g}·x² + {p[1]:.4g}·x + {p[2]:.4g}", None),
        "poly3": (None, ["a", "b", "c", "d"], lambda p: f"y = {p[0]:.4g}·x³ + {p[1]:.4g}·x² + {p[2]:.4g}·x + {p[3]:.4g}", None),
    }
    if model not in fit_funcs:
        raise ValueError(f"未知模型: {model}")

    func, param_names, eq_fmt, default_p0 = fit_funcs[model]
    if model in {"poly2", "poly3"}:
        deg = 2 if model == "poly2" else 3
        coeffs = np.polyfit(x, y, deg)
        popt = coeffs.tolist()
        y_fit = np.polyval(coeffs, x)
        cov = None
    else:
        if p0 is None:
            p0 = default_p0
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Covariance of the parameters could not be estimated", category=OptimizeWarning)
                popt, pcov = _cf(func, x, y, p0=p0, maxfev=10000)
        except RuntimeError as exc:
            raise RuntimeError(f"拟合未收敛: {exc}")
        y_fit = func(x, *popt)
        cov = pcov.tolist() if pcov is not None else None

    ss_res = float(np.sum((y - y_fit) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    x_dense = np.linspace(x.min(), x.max(), 300)
    y_dense = np.polyval(np.array(popt), x_dense).tolist() if model in {"poly2", "poly3"} else func(x_dense, *popt).tolist()
    return {
        "model": model,
        "params": [float(v) for v in popt],
        "param_names": param_names,
        "r2": r2,
        "fit_x": x_dense.tolist(),
        "fit_y": y_dense,
        "equation": eq_fmt(popt),
        "covariance": cov,
    }


def _power_func(x, a, b):
    import numpy as np
    return a * np.abs(x) ** b


def detect_peaks(
    xs: List[float],
    ys: List[float],
    min_height: Optional[float] = None,
    min_distance: Optional[int] = 1,
    min_distance_x: Optional[float] = None,
    prominence: Optional[float] = None,
) -> Dict[str, Any]:
    try:
        import numpy as np
        from scipy.signal import find_peaks
    except ImportError:
        raise ImportError("需要 numpy 和 scipy")

    y = np.array(ys)
    kwargs: Dict[str, Any] = {}
    if min_distance is not None:
        kwargs["distance"] = max(1, int(min_distance))
    if min_height is not None:
        kwargs["height"] = min_height
    if prominence is not None:
        kwargs["prominence"] = prominence
    indices, _props = find_peaks(y, **kwargs)
    if min_distance_x is not None and min_distance_x > 0:
        indices = _filter_indices_by_x_distance(xs, ys, indices, min_distance_x, prefer="higher")
    peaks = [{"x": xs[index], "y": ys[index], "index": int(index)} for index in indices]
    return {"peaks": peaks, "count": len(peaks)}


def detect_valleys(
    xs: List[float],
    ys: List[float],
    min_depth: Optional[float] = None,
    min_distance: Optional[int] = 1,
    min_distance_x: Optional[float] = None,
    prominence: Optional[float] = None,
) -> Dict[str, Any]:
    try:
        import numpy as np
        from scipy.signal import find_peaks
    except ImportError:
        raise ImportError("需要 numpy 和 scipy")

    y = np.array(ys)
    kwargs: Dict[str, Any] = {}
    if min_distance is not None:
        kwargs["distance"] = max(1, int(min_distance))
    if min_depth is not None:
        kwargs["height"] = min_depth
    if prominence is not None:
        kwargs["prominence"] = prominence
    indices, _ = find_peaks(-y, **kwargs)
    if min_distance_x is not None and min_distance_x > 0:
        indices = _filter_indices_by_x_distance(xs, ys, indices, min_distance_x, prefer="lower")
    valleys = [{"x": xs[index], "y": ys[index], "index": int(index)} for index in indices]
    return {"valleys": valleys, "count": len(valleys)}


def _filter_indices_by_x_distance(xs: List[float], ys: List[float], indices, min_distance_x: float, *, prefer: str) -> List[int]:
    if min_distance_x <= 0:
        return [int(index) for index in indices]
    ordered = [int(index) for index in indices]
    ranked = sorted(ordered, key=(lambda index: (ys[index], xs[index])) if prefer == "lower" else (lambda index: (-ys[index], xs[index])))
    kept: List[int] = []
    for index in ranked:
        x_value = xs[index]
        if all(abs(x_value - xs[kept_index]) >= min_distance_x for kept_index in kept):
            kept.append(index)
    return sorted(kept)


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


def register_extensions(registry) -> None:
    del registry
