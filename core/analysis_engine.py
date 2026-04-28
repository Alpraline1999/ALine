"""
分析引擎 — 曲线拟合 / 峰值检测 / 统计 / 相关性

所有函数输入 List[float]，输出结构化 dict 结果。
使用 scipy 时自动导入；纯 Python 回退仅覆盖基础统计。
"""
from __future__ import annotations

import math
import warnings
from typing import Any, Dict, List, Optional, Tuple

from core.extension_api import extension_registry, invoke_analysis_extension_handler
from extensions.processing.extension_tools import line_from_xy

# ─────────────────────────────────────────────────────────────
# 曲线拟合
# ─────────────────────────────────────────────────────────────

_FIT_MODELS = {
    "线性 (ax+b)":          "linear",
    "幂函数 (a·x^b)":       "power",
    "指数 (a·e^(bx))":      "exponential",
    "高斯 (a·exp(-(x-μ)²/2σ²))": "gaussian",
    "2次多项式":             "poly2",
    "3次多项式":             "poly3",
}
FIT_MODEL_LABELS = list(_FIT_MODELS.keys())
FIT_MODEL_TYPES  = list(_FIT_MODELS.values())


def fit_curve(
    xs: List[float],
    ys: List[float],
    model: str,
    p0: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """拟合曲线，返回包含参数、R² 和拟合曲线坐标的 dict。

    Returns:
        {
          "model": str,
          "params": List[float],
          "param_names": List[str],
          "r2": float,
          "fit_x": List[float],
          "fit_y": List[float],
          "equation": str,
          "covariance": List[List[float]] | None,
        }
    """
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
        "linear":      (lambda x, a, b: a * x + b,
                        ["a", "b"],
                        lambda p: f"y = {p[0]:.4g}·x + {p[1]:.4g}",
                        [1.0, 0.0]),
        "power":       (_power_func,
                        ["a", "b"],
                        lambda p: f"y = {p[0]:.4g}·x^{p[1]:.4g}",
                        [1.0, 1.0]),
        "exponential": (lambda x, a, b: a * np.exp(b * x),
                        ["a", "b"],
                        lambda p: f"y = {p[0]:.4g}·e^({p[1]:.4g}·x)",
                        [1.0, 0.01]),
        "gaussian":    (lambda x, a, mu, sig: a * np.exp(-((x - mu) ** 2) / (2 * sig ** 2)),
                        ["a", "μ", "σ"],
                        lambda p: f"y = {p[0]:.4g}·exp(-(x-{p[1]:.4g})²/2·{p[2]:.4g}²)",
                        [max(y), float(x.mean()), float(x.std()) or 1.0]),
        "poly2":       (None, ["a", "b", "c"],
                        lambda p: f"y = {p[0]:.4g}·x² + {p[1]:.4g}·x + {p[2]:.4g}",
                        None),
        "poly3":       (None, ["a", "b", "c", "d"],
                        lambda p: (f"y = {p[0]:.4g}·x³ + {p[1]:.4g}·x² "
                                   f"+ {p[2]:.4g}·x + {p[3]:.4g}"),
                        None),
    }

    if model not in fit_funcs:
        raise ValueError(f"未知模型: {model}")

    func, param_names, eq_fmt, default_p0 = fit_funcs[model]

    if model in ("poly2", "poly3"):
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
                warnings.filterwarnings(
                    "ignore",
                    message="Covariance of the parameters could not be estimated",
                    category=OptimizeWarning,
                )
                popt, pcov = _cf(func, x, y, p0=p0, maxfev=10000)
        except RuntimeError as e:
            raise RuntimeError(f"拟合未收敛: {e}")
        y_fit = func(x, *popt)
        cov = pcov.tolist() if pcov is not None else None

    ss_res = float(np.sum((y - y_fit) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    x_dense = np.linspace(x.min(), x.max(), 300)
    if model in ("poly2", "poly3"):
        y_dense = np.polyval(np.array(popt), x_dense).tolist()
    else:
        y_dense = func(x_dense, *popt).tolist()

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


# ─────────────────────────────────────────────────────────────
# 峰值检测
# ─────────────────────────────────────────────────────────────

def detect_peaks(
    xs: List[float],
    ys: List[float],
    min_height: Optional[float] = None,
    min_distance: Optional[int] = 1,
    min_distance_x: Optional[float] = None,
    prominence: Optional[float] = None,
) -> Dict[str, Any]:
    """使用 scipy.signal.find_peaks 检测峰值。

    Returns:
        {"peaks": [{"x": float, "y": float, "index": int}, ...], "count": int}
    """
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

    indices, props = find_peaks(y, **kwargs)
    if min_distance_x is not None and min_distance_x > 0:
        indices = _filter_indices_by_x_distance(xs, ys, indices, min_distance_x, prefer="higher")
    peaks = [{"x": xs[i], "y": ys[i], "index": int(i)} for i in indices]
    return {"peaks": peaks, "count": len(peaks)}


def detect_valleys(
    xs: List[float],
    ys: List[float],
    min_depth: Optional[float] = None,
    min_distance: Optional[int] = 1,
    min_distance_x: Optional[float] = None,
    prominence: Optional[float] = None,
) -> Dict[str, Any]:
    """检测波谷（对 y 取反后用 find_peaks）。

    Returns:
        {"valleys": [{"x": float, "y": float, "index": int}, ...], "count": int}
    """
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
    valleys = [{"x": xs[i], "y": ys[i], "index": int(i)} for i in indices]
    return {"valleys": valleys, "count": len(valleys)}


def _filter_indices_by_x_distance(
    xs: List[float],
    ys: List[float],
    indices,
    min_distance_x: float,
    *,
    prefer: str,
) -> List[int]:
    if min_distance_x <= 0:
        return [int(index) for index in indices]

    ordered = [int(index) for index in indices]
    if prefer == "lower":
        ranked = sorted(ordered, key=lambda index: (ys[index], xs[index]))
    else:
        ranked = sorted(ordered, key=lambda index: (-ys[index], xs[index]))

    kept: List[int] = []
    for index in ranked:
        x_value = xs[index]
        if all(abs(x_value - xs[kept_index]) >= min_distance_x for kept_index in kept):
            kept.append(index)
    return sorted(kept)


# ─────────────────────────────────────────────────────────────
# 统计
# ─────────────────────────────────────────────────────────────

def compute_statistics(xs: List[float], ys: List[float]) -> Dict[str, Any]:
    """基础统计量：N, x/y 的 min/max/mean/std/median/percentiles."""
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
            std = math.sqrt(sum((v - mean) ** 2 for v in vals) / n)
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


# ─────────────────────────────────────────────────────────────
# 相关性
# ─────────────────────────────────────────────────────────────

def compute_correlation(
    ys1: List[float],
    ys2: List[float],
    method: str = "pearson",
) -> Dict[str, Any]:
    """计算两序列的相关系数。

    Args:
        method: "pearson" | "spearman"
    Returns:
        {"method": str, "r": float, "p_value": float | None}
    """
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

    # Pearson (fallback numpy → pure Python)
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


def compute_error_metrics(
    xs1: List[float],
    ys1: List[float],
    xs2: List[float],
    ys2: List[float],
) -> Dict[str, Any]:
    """计算两条序列按索引对齐后的误差指标与误差曲线。"""
    n = min(len(xs1), len(ys1), len(xs2), len(ys2))
    if n < 2:
        raise ValueError("误差比较至少需要 2 个对齐数据点")

    xs = list(xs1[:n])
    ref = list(ys1[:n])
    cmp = list(ys2[:n])
    error_y = [a - b for a, b in zip(ref, cmp)]
    abs_error = [abs(v) for v in error_y]

    mae = sum(abs_error) / n
    rmse = math.sqrt(sum(v * v for v in error_y) / n)
    mean_error = sum(error_y) / n
    max_abs_error = max(abs_error)

    relative_errors = [abs(err / base) for err, base in zip(error_y, ref) if base not in (0, 0.0)]
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


def run_analysis(
    analysis_type: str,
    inputs: List[Dict[str, Any]],
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    params = dict(params or {})
    normalized_inputs = [
        {
            "x": list(item.get("x", []) or []),
            "y": list(item.get("y", []) or []),
            "name": item.get("name", ""),
        }
        for item in inputs
    ]
    custom_analysis = extension_registry.get_analysis(analysis_type)
    if custom_analysis is not None:
        return invoke_analysis_extension_handler(custom_analysis.handler, normalized_inputs, params)
    if analysis_type == "curve_fit":
        if not normalized_inputs:
            raise ValueError("curve_fit 需要至少一条输入数据")
        first = normalized_inputs[0]
        model = params.get("model", "linear")
        result = fit_curve(first["x"], first["y"], model, params.get("p0"))
        result["analysis_type"] = "curve_fit"
        result["source_name"] = first.get("name", "")
        result["summary_items"] = [
            {"label": "模型", "value": result.get("model", "")},
            {"label": "方程", "value": result.get("equation", "")},
            {"label": "R²", "value": result.get("r2")},
            {"label": "数据源", "value": result.get("source_name", "")},
        ]
        param_names = list(result.get("param_names", []) or [])
        param_values = list(result.get("params", []) or [])
        if param_names and param_values:
            result["table_sections"] = [
                {
                    "title": "拟合参数",
                    "headers": ["参数", "值"],
                    "rows": [[name, value] for name, value in zip(param_names, param_values)],
                }
            ]
        result["lines"] = [
            {"line_name": "拟合曲线", "line": line_from_xy(result.get("fit_x", []), result.get("fit_y", []))},
        ]
        result["_plot_series"] = [
            {
                "name": result.get("source_name") or "原始数据",
                "line": line_from_xy(first["x"], first["y"]),
                "kind": "scatter",
                "color": "#888888",
                "alpha": 0.7,
                "size": 15,
            },
            {"name": "拟合曲线", "line": "拟合曲线", "color": "#D13438", "line_width": 2.0},
        ]
        return result
    if analysis_type == "peak_detect":
        if not normalized_inputs:
            raise ValueError("peak_detect 需要至少一条输入数据")
        first = normalized_inputs[0]
        result = detect_peaks(
            first["x"],
            first["y"],
            min_height=params.get("min_height"),
            min_distance=params.get("min_distance", 1),
            min_distance_x=params.get("min_distance_x"),
            prominence=params.get("prominence"),
        )
        valleys = detect_valleys(
            first["x"],
            first["y"],
            min_depth=params.get("min_depth"),
            min_distance=params.get("min_distance", 1),
            min_distance_x=params.get("min_distance_x"),
            prominence=params.get("prominence"),
        )
        result["valleys"] = valleys.get("valleys", [])
        result["valley_count"] = valleys.get("count", 0)
        result["analysis_type"] = "peak_detect"
        result["source_name"] = first.get("name", "")
        distance_mode = "x_distance" if params.get("min_distance_x") not in (None, "") else "points"
        distance_value = params.get("min_distance_x") if distance_mode == "x_distance" else params.get("min_distance", 1)
        result["distance_mode"] = distance_mode
        result["distance_value"] = distance_value
        result["summary_items"] = [
            {"label": "波峰数量", "value": result.get("count", 0)},
            {"label": "波谷数量", "value": result.get("valley_count", 0)},
            {"label": "数据源", "value": result.get("source_name", "")},
        ]
        if distance_value not in (None, ""):
            result["summary_items"].append(
                {
                    "label": "最小间距",
                    "value": f"{distance_value}（{'X 值间距' if distance_mode == 'x_distance' else '采样点数'}）",
                }
            )
        peak_points = list(result.get("peaks", []) or [])
        valley_points = list(result.get("valleys", []) or [])
        merged_points = [
            {"type": "波峰", "x": point.get("x"), "y": point.get("y")}
            for point in peak_points
        ] + [
            {"type": "波谷", "x": point.get("x"), "y": point.get("y")}
            for point in valley_points
        ]
        merged_points.sort(key=lambda item: (float("inf") if item.get("x") is None else item.get("x"), item.get("type") != "波峰"))
        if merged_points:
            result["table_sections"] = [
                {
                    "title": "峰谷列表",
                    "headers": ["序号", "类型", "X", "Y"],
                    "rows": [[index + 1, item.get("type"), item.get("x"), item.get("y")] for index, item in enumerate(merged_points)],
                }
            ]
        plot_series: List[Dict[str, Any]] = [
            {
                "name": result.get("source_name") or "原始数据",
                "line": line_from_xy(first["x"], first["y"]),
                "kind": "line",
                "color": "#0078D4",
                "line_width": 1.4,
            }
        ]
        result_lines: List[Dict[str, Any]] = []
        if merged_points:
            merged_line_points = [
                (float(item["x"]), float(item["y"]))
                for item in merged_points
                if item.get("x") is not None and item.get("y") is not None
            ]
            result_lines.append(
                {
                    "line_name": "峰谷点",
                    "line": line_from_xy(
                        [point[0] for point in merged_line_points],
                        [point[1] for point in merged_line_points],
                    ),
                }
            )
            plot_series.append(
                {
                    "name": f"峰谷 ({len(merged_points)}个)",
                    "line": "峰谷点",
                    "kind": "markers",
                    "marker": "o",
                    "size": 42,
                    "color": "#605E5C",
                }
            )
        if peak_points:
            result_lines.append(
                {
                    "line_name": "波峰点",
                    "line": line_from_xy([point.get("x") for point in peak_points], [point.get("y") for point in peak_points]),
                }
            )
            plot_series.append(
                {
                    "name": f"波峰 ({len(peak_points)}个)",
                    "line": "波峰点",
                    "kind": "markers",
                    "marker": "^",
                    "size": 50,
                    "color": "#D13438",
                }
            )
        if valley_points:
            result_lines.append(
                {
                    "line_name": "波谷点",
                    "line": line_from_xy([point.get("x") for point in valley_points], [point.get("y") for point in valley_points]),
                }
            )
            plot_series.append(
                {
                    "name": f"波谷 ({len(valley_points)}个)",
                    "line": "波谷点",
                    "kind": "markers",
                    "marker": "v",
                    "size": 50,
                    "color": "#107C10",
                }
            )
        if result_lines:
            result["lines"] = result_lines
        result["_plot_series"] = plot_series
        return result
    if analysis_type == "statistics":
        if not normalized_inputs:
            raise ValueError("statistics 需要至少一条输入数据")
        first = normalized_inputs[0]
        result = compute_statistics(first["x"], first["y"])
        result["analysis_type"] = "statistics"
        result["source_name"] = first.get("name", "")
        result["summary_items"] = [
            {"label": "样本数 N", "value": result.get("n", 0)},
            {"label": "X 均值", "value": result.get("x_mean", 0)},
            {"label": "X 标准差", "value": result.get("x_std", 0)},
            {"label": "X 范围", "value": f"[{result.get('x_min', 0):.4g}, {result.get('x_max', 0):.4g}]"},
            {"label": "Y 均值", "value": result.get("y_mean", 0)},
            {"label": "Y 标准差", "value": result.get("y_std", 0)},
            {"label": "Y 范围", "value": f"[{result.get('y_min', 0):.4g}, {result.get('y_max', 0):.4g}]"},
            {"label": "Y 中位数", "value": result.get("y_median", 0)},
            {"label": "Y 四分位", "value": f"Q1={result.get('y_p25', 0):.4g}, Q3={result.get('y_p75', 0):.4g}"},
        ]
        if first["x"]:
            mean = float(result.get("y_mean", 0.0))
            result["_plot_series"] = [
                {
                    "name": result.get("source_name") or "原始数据",
                    "line": line_from_xy(first["x"], first["y"]),
                    "kind": "line",
                    "color": "#0078D4",
                    "line_width": 1.4,
                },
                {
                    "name": f"均值={mean:.4g}",
                    "line": line_from_xy([first["x"][0], first["x"][-1]], [mean, mean]),
                    "kind": "line",
                    "color": "#D13438",
                    "line_width": 1.0,
                    "line_style": "--",
                },
            ]
        return result
    if analysis_type == "correlation":
        if len(normalized_inputs) < 2:
            raise ValueError("correlation 需要两条输入数据")
        first, second = normalized_inputs[:2]
        result = compute_correlation(first["y"], second["y"], str(params.get("method", "pearson")))
        result["analysis_type"] = "correlation"
        result["name1"] = first.get("name", "")
        result["name2"] = second.get("name", "")
        result["summary_items"] = [
            {"label": "方法", "value": result.get("method", "")},
            {"label": "相关系数 r", "value": result.get("r", 0)},
            {"label": "数据", "value": f"{result.get('name1', '')} vs {result.get('name2', '')}"},
        ]
        if result.get("p_value") is not None:
            result["summary_items"].append({"label": "p 值", "value": result.get("p_value")})
        point_count = min(len(first["y"]), len(second["y"]))
        if point_count:
            result["_plot_series"] = [
                {
                    "name": f"{result.get('name1', '数据1')} vs {result.get('name2', '数据2')}",
                    "line": line_from_xy(first["y"][:point_count], second["y"][:point_count]),
                    "kind": "scatter",
                    "color": "#0078D4",
                    "alpha": 0.7,
                    "size": 15,
                }
            ]
            result["x_label"] = result.get("name1", "")
            result["y_label"] = result.get("name2", "")
            result["plot_title"] = f"r = {result.get('r', 0):.4f}"
        return result
    if analysis_type == "error_compare":
        if len(normalized_inputs) < 2:
            raise ValueError("error_compare 需要两条输入数据")
        first, second = normalized_inputs[:2]
        result = compute_error_metrics(first["x"], first["y"], second["x"], second["y"])
        result["name1"] = first.get("name", "")
        result["name2"] = second.get("name", "")
        result["summary_items"] = [
            {"label": "数据", "value": f"{result.get('name1', '')} vs {result.get('name2', '')}"},
            {"label": "MAE", "value": result.get("mae", 0)},
            {"label": "RMSE", "value": result.get("rmse", 0)},
            {"label": "平均误差", "value": result.get("mean_error", 0)},
            {"label": "最大绝对误差", "value": result.get("max_abs_error", 0)},
        ]
        if result.get("relative_mae") is not None:
            result["summary_items"].append({"label": "相对平均误差", "value": result.get("relative_mae")})
        result["lines"] = [
            {"line_name": "误差曲线", "line": line_from_xy(result.get("error_x", []), result.get("error_y", []))},
        ]
        result["_plot_series"] = [
            {"name": "误差", "line": "误差曲线", "color": "#D13438", "line_width": 1.5}
        ]
        result["x_label"] = result.get("name1", "")
        result["y_label"] = "误差"
        return result
    raise ValueError(f"未知分析类型: {analysis_type}")


# ─────────────────────────────────────────────────────────────
# 报告渲染（v0.3）
# ─────────────────────────────────────────────────────────────

_BUILTIN_ANALYSIS_LABELS = {
    "curve_fit": "曲线拟合",
    "peak_detect": "峰值检测",
    "statistics": "统计分析",
    "correlation": "相关性分析",
    "error_compare": "误差比较",
}


_REPORT_TEMPLATE_PLACEHOLDERS: List[Dict[str, str]] = [
    {"token": "{{date}}", "group": "通用", "label": "日期", "description": "当前日期时间"},
    {"token": "{{result_count}}", "group": "通用", "label": "结果数量", "description": "当前报告上下文中的结果数量"},
    {"token": "{{result_names}}", "group": "通用", "label": "结果名称", "description": "当前结果名称列表"},
    {"token": "{{analysis_type}}", "group": "通用", "label": "分析类型", "description": "分析类型名称"},
    {"token": "{{source_name}}", "group": "通用", "label": "数据来源", "description": "结果对应的数据来源名称"},
    {"token": "{{table:analysis_results}}", "group": "通用", "label": "结果概览表", "description": "多结果概览 Markdown 表格"},
    {"token": "{{multi_result_sections}}", "group": "通用", "label": "多结果详情", "description": "多结果模式下的分节摘要"},
    {"token": "{{model}}", "group": "曲线拟合", "label": "拟合模型", "description": "拟合分析使用的模型名"},
    {"token": "{{equation}}", "group": "曲线拟合", "label": "拟合方程", "description": "拟合结果方程"},
    {"token": "{{r2}}", "group": "曲线拟合", "label": "R²", "description": "拟合优度，默认保留 4 位小数"},
    {"token": "{{r2:.4f}}", "group": "曲线拟合", "label": "R² 自定义精度", "description": "示例格式，支持按需修改小数位数"},
    {"token": "{{table:params}}", "group": "曲线拟合", "label": "拟合参数表", "description": "拟合参数 Markdown 表格"},
    {"token": "{{peak_count}}", "group": "峰值检测", "label": "峰值个数", "description": "峰值检测结果中的峰值数量"},
    {"token": "{{valley_count}}", "group": "峰值检测", "label": "波谷个数", "description": "峰值检测结果中的波谷数量"},
    {"token": "{{table:peaks}}", "group": "峰值检测", "label": "峰值表", "description": "峰值列表 Markdown 表格"},
    {"token": "{{table:valleys}}", "group": "峰值检测", "label": "波谷表", "description": "波谷列表 Markdown 表格"},
    {"token": "{{n}}", "group": "统计分析", "label": "样本数", "description": "统计分析中的数据点数量"},
    {"token": "{{y_mean}}", "group": "统计分析", "label": "Y 均值", "description": "Y 值均值"},
    {"token": "{{y_std}}", "group": "统计分析", "label": "Y 标准差", "description": "Y 值标准差"},
    {"token": "{{x_min}}", "group": "统计分析", "label": "X 最小值", "description": "X 范围下界"},
    {"token": "{{x_max}}", "group": "统计分析", "label": "X 最大值", "description": "X 范围上界"},
    {"token": "{{y_min}}", "group": "统计分析", "label": "Y 最小值", "description": "Y 范围下界"},
    {"token": "{{y_max}}", "group": "统计分析", "label": "Y 最大值", "description": "Y 范围上界"},
    {"token": "{{name1}}", "group": "相关性分析", "label": "主数据名称", "description": "双输入分析中的主输入数据名称"},
    {"token": "{{name2}}", "group": "相关性分析", "label": "对比数据名称", "description": "双输入分析中的对比数据名称"},
    {"token": "{{r}}", "group": "相关性分析", "label": "相关系数", "description": "相关性分析中的 r 值"},
    {"token": "{{mae}}", "group": "误差比较", "label": "MAE", "description": "误差分析中的平均绝对误差"},
    {"token": "{{rmse}}", "group": "误差比较", "label": "RMSE", "description": "误差分析中的均方根误差"},
    {"token": "{{mean_error}}", "group": "误差比较", "label": "平均误差", "description": "误差分析中的平均误差"},
    {"token": "{{max_abs_error}}", "group": "误差比较", "label": "最大绝对误差", "description": "误差分析中的最大绝对误差"},
    {"token": "{{relative_mae}}", "group": "误差比较", "label": "相对平均误差", "description": "误差分析中的相对平均误差"},
]


def _is_placeholder_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) and not isinstance(value, complex)


def _normalize_report_placeholder_token(value: Any) -> str:
    clean_value = str(value or "").strip()
    if not clean_value:
        return ""
    if clean_value.startswith("{{") and clean_value.endswith("}}"):
        return clean_value
    clean_value = clean_value.strip("{} ")
    return f"{{{{{clean_value}}}}}" if clean_value else ""


def _placeholder_key_from_token(token: str) -> str:
    clean_token = str(token or "").strip()
    if clean_token.startswith("{{") and clean_token.endswith("}}"):
        clean_token = clean_token[2:-2]
    if ":" in clean_token:
        clean_token = clean_token.split(":", 1)[0]
    return clean_token.strip()


def _analysis_extension_report_placeholders() -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    for extension in sorted(extension_registry.list_analysis(), key=lambda item: item.name.casefold()):
        for raw_item in list(getattr(extension, "report_placeholders", []) or []):
            if isinstance(raw_item, str):
                token = _normalize_report_placeholder_token(raw_item)
                label = _placeholder_key_from_token(token)
                description = f"{extension.name} 结果字段 {label}"
            elif isinstance(raw_item, dict):
                token = _normalize_report_placeholder_token(raw_item.get("token") or raw_item.get("key"))
                label = str(raw_item.get("label") or raw_item.get("key") or _placeholder_key_from_token(token)).strip()
                description = str(raw_item.get("description") or f"{extension.name} 结果字段 {_placeholder_key_from_token(token)}").strip()
            else:
                continue
            if not token:
                continue
            entries.append({
                "token": token,
                "group": extension.name,
                "label": label or _placeholder_key_from_token(token),
                "description": description,
            })
    return entries


def _dynamic_placeholder_group(context: Dict[str, Any]) -> str:
    analysis_type = str(context.get("analysis_type") or "").strip()
    extension = extension_registry.get_analysis(analysis_type)
    if extension is not None:
        return extension.name
    return _BUILTIN_ANALYSIS_LABELS.get(analysis_type, "通用")


def _dynamic_report_template_placeholders(result: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    if not isinstance(result, dict):
        return []

    reserved_tokens = {
        item["token"] for item in _REPORT_TEMPLATE_PLACEHOLDERS + _analysis_extension_report_placeholders()
    }
    contexts = [result]
    primary = result.get("_primary_result")
    if isinstance(primary, dict) and primary is not result:
        contexts.append(primary)

    entries: List[Dict[str, str]] = []
    seen_keys: set[str] = set()
    for context in contexts:
        for key in sorted(context.keys(), key=str.casefold):
            if key.startswith("_") or key in seen_keys:
                continue
            token = f"{{{{{key}}}}}"
            value = context.get(key)
            if token in reserved_tokens or not _is_placeholder_scalar(value):
                continue
            seen_keys.add(key)
            entries.append({
                "token": token,
                "group": _dynamic_placeholder_group(context),
                "label": key,
                "description": f"扩展结果字段 {key}",
            })
    return entries


def list_report_template_placeholders(result: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    merged: List[Dict[str, str]] = []
    seen_tokens: set[str] = set()
    for source_entries in (
        [dict(item) for item in _REPORT_TEMPLATE_PLACEHOLDERS],
        _analysis_extension_report_placeholders(),
        _dynamic_report_template_placeholders(result),
    ):
        for entry in source_entries:
            token = str(entry.get("token") or "").strip()
            if not token or token in seen_tokens:
                continue
            seen_tokens.add(token)
            merged.append(dict(entry))
    return merged

def render_report(template_content: str, result: Optional[Dict[str, Any]]) -> str:
    """将 Markdown 报告模板中的占位符替换为实际分析结果。

    支持占位符（均用 {{key}} 形式）：
    - {{date}}              当前日期
    - {{result_count}}      结果数量
    - {{result_names}}      结果名称列表
    - {{analysis_type}}     分析类型名称
    - {{model}}             拟合模型名（curve_fit）
    - {{equation}}          拟合方程（curve_fit）
    - {{r2}}                R²值（curve_fit，保留4位）
    - {{r2:.Nf}}            R²值（自定义精度）
    - {{n}}                 数据点数（statistics）
    - {{y_mean}}            Y 均值
    - {{y_std}}             Y 标准差
    - {{y_min}},{{y_max}}   Y 范围
    - {{x_mean}}            X 均值
    - {{x_std}}             X 标准差
    - {{x_min}},{{x_max}}   X 范围
    - {{r}}                 相关系数（correlation）
    - {{peak_count}}        峰值个数（peak_detect）
    - {{valley_count}}      波谷个数（peak_detect）
    - {{name1}},{{name2}}   双输入分析数据名
    - {{mae}},{{rmse}}      误差比较指标
    - {{mean_error}}        平均误差
    - {{max_abs_error}}     最大绝对误差
    - {{relative_mae}}      相对平均误差
    - {{table:analysis_results}} 结果概览表
    - {{multi_result_sections}}  多结果详情摘要
    - {{table:params}}      参数表格（Markdown 格式）
    - {{table:peaks}}       峰值列表
    - {{table:valleys}}     波谷列表
    """
    from datetime import datetime
    import re

    if not template_content:
        return ""
    context = result or {}
    r = context.get("_primary_result", context) if isinstance(context, dict) else {}
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 基本替换字典
    _type_names = {
        "curve_fit": "曲线拟合",
        "peak_detect": "峰值检测",
        "statistics": "统计分析",
        "correlation": "相关性分析",
        "error_compare": "误差比较",
        "spectrum_analysis": "频谱分析",
    }
    subs = {
        "date": now,
        "result_count": str(context.get("result_count", 1 if r else 0)),
        "result_names": str(context.get("result_names", context.get("name1", ""))),
        "analysis_type": _type_names.get(r.get("analysis_type", ""), r.get("analysis_type", "")),
        "model": r.get("model", ""),
        "equation": r.get("equation", ""),
        "r2": f"{r.get('r2', float('nan')):.4f}",
        "n": str(r.get("n", "")),
        "y_mean": f"{r.get('y_mean', 0):.6g}",
        "y_std": f"{r.get('y_std', 0):.6g}",
        "y_min": f"{r.get('y_min', 0):.6g}",
        "y_max": f"{r.get('y_max', 0):.6g}",
        "x_mean": f"{r.get('x_mean', 0):.6g}",
        "x_std": f"{r.get('x_std', 0):.6g}",
        "x_min": f"{r.get('x_min', 0):.6g}",
        "x_max": f"{r.get('x_max', 0):.6g}",
        "r": f"{r.get('r', float('nan')):.6f}",
        "peak_count": str(r.get("count", 0)),
        "valley_count": str(r.get("valley_count", 0)),
        "source_name": r.get("source_name", ""),
        "name1": r.get("name1", ""),
        "name2": r.get("name2", ""),
        "mae": f"{r.get('mae', 0):.6f}",
        "rmse": f"{r.get('rmse', 0):.6f}",
        "mean_error": f"{r.get('mean_error', 0):.6f}",
        "max_abs_error": f"{r.get('max_abs_error', 0):.6f}",
        "relative_mae": f"{r.get('relative_mae', 0):.6f}" if r.get("relative_mae") is not None else "",
        "multi_result_sections": str(context.get("multi_result_sections", "")),
    }

    # 处理 {{r2:.Nf}} 自定义精度
    def _fmt_r2(m):
        fmt = m.group(1)
        try:
            return f"{r.get('r2', float('nan')):{fmt}}"
        except Exception:
            return m.group(0)
    content = re.sub(r"\{\{r2:([^}]+)\}\}", _fmt_r2, template_content)

    # 简单 {{key}} 替换
    for k, v in subs.items():
        content = content.replace("{{" + k + "}}", v)

    content = content.replace(
        "{{table:analysis_results}}",
        str(context.get("_analysis_results_table", "_（无分析结果）_")),
    )

    # {{table:params}} — 拟合参数表格
    params = r.get("params", [])
    param_names = r.get("param_names", [])
    if params and param_names:
        rows = ["| 参数 | 值 |", "|------|-----|"]
        rows += [f"| {n} | {v:.6g} |" for n, v in zip(param_names, params)]
        content = content.replace("{{table:params}}", "\n".join(rows))
    else:
        content = content.replace("{{table:params}}", "_（无拟合参数）_")

    # {{table:peaks}} — 峰值列表
    peaks = r.get("peaks", [])
    if peaks:
        rows = ["| # | X | Y |", "|---|---|---|"]
        rows += [f"| {i+1} | {p['x']:.6g} | {p['y']:.6g} |" for i, p in enumerate(peaks[:50])]
        content = content.replace("{{table:peaks}}", "\n".join(rows))
    else:
        content = content.replace("{{table:peaks}}", "_（无峰值数据）_")

    valleys = r.get("valleys", [])
    if valleys:
        rows = ["| # | X | Y |", "|---|---|---|"]
        rows += [f"| {i+1} | {p['x']:.6g} | {p['y']:.6g} |" for i, p in enumerate(valleys[:50])]
        content = content.replace("{{table:valleys}}", "\n".join(rows))
    else:
        content = content.replace("{{table:valleys}}", "_（无波谷数据）_")

    def _format_generic_placeholder(value: Any, fmt_spec: Optional[str] = None) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "True" if value else "False"
        if isinstance(value, int) and not isinstance(value, bool):
            return format(value, fmt_spec) if fmt_spec else str(value)
        if isinstance(value, float):
            if fmt_spec:
                try:
                    return format(value, fmt_spec)
                except Exception:
                    return str(value)
            return f"{value:.6g}"
        if isinstance(value, (list, tuple)) and all(not isinstance(item, (dict, list, tuple, set)) for item in value):
            return ", ".join(_format_generic_placeholder(item) for item in value)
        return str(value)

    def _replace_generic_placeholder(match):
        key = match.group(1)
        fmt_spec = match.group(2)
        if key.startswith("_"):
            return ""
        if isinstance(context, dict) and key in context:
            return _format_generic_placeholder(context.get(key), fmt_spec)
        if isinstance(r, dict) and key in r:
            return _format_generic_placeholder(r.get(key), fmt_spec)
        return ""

    content = re.sub(r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)(?::([^}]+))?\}\}", _replace_generic_placeholder, content)

    # 清理未替换的占位符
    content = re.sub(r"\{\{[^}]+\}\}", "_（N/A）_", content)
    return content


_DEFAULT_REPORT_TEMPLATE = """\
# 数据分析报告

**日期：** {{date}}

**结果数量：** {{result_count}}

**结果名称：** {{result_names}}

**分析类型：** {{analysis_type}}

**数据来源：** {{source_name}}

---

## 结果概览

{{table:analysis_results}}

## 结果详情

{{multi_result_sections}}

---

## 常用占位符

- 基础信息: {{date}}, {{result_count}}, {{result_names}}, {{analysis_type}}, {{source_name}}, {{name1}}, {{name2}}
- 拟合结果: {{model}}, {{equation}}, {{r2}}, {{table:params}}
- 峰谷检测: {{peak_count}}, {{valley_count}}, {{table:peaks}}, {{table:valleys}}
- 统计结果: {{n}}, {{x_mean}}, {{x_std}}, {{x_min}}, {{x_max}}, {{y_mean}}, {{y_std}}, {{y_min}}, {{y_max}}
- 相关性/误差: {{r}}, {{mae}}, {{rmse}}, {{mean_error}}, {{max_abs_error}}, {{relative_mae}}
"""

