from __future__ import annotations

import json
import warnings
from typing import Any, Dict, List, Optional

from core.extension_api import AnalysisExtension, ExtensionConfigField
from processing.extension_tools import line_xy, primary_line


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


def _power_func(x, a, b):
    import numpy as np

    return a * np.abs(x) ** b


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


def _handler(lines, params):
    if not lines:
        raise ValueError("curve_fit 需要至少一条输入数据")
    xs, ys = line_xy(primary_line(lines))
    result = fit_curve(
        xs,
        ys,
        str(params.get("model", "linear") or "linear"),
        parse_optional_json_list(params.get("p0")),
    )
    result["analysis_type"] = "curve_fit"
    return result


def register_extensions(registry) -> None:
    registry.register_analysis(
        AnalysisExtension(
            type="curve_fit",
            name="曲线拟合",
            handler=_handler,
            description="对当前曲线执行模型拟合，并输出参数与拟合曲线。",
            version=VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            config_fields=[
                ExtensionConfigField(
                    key="model",
                    label="拟合模型",
                    description="选择拟合模型，默认使用线性模型。",
                    field_type="selective",
                    default="linear",
                    choices=("linear", "power", "exponential", "gaussian", "poly2", "poly3"),
                ),
                ExtensionConfigField(
                    key="p0",
                    label="初始参数",
                    description="可选；以 JSON 列表形式提供初始猜测参数。",
                    field_type="string",
                    default=None,
                    placeholder="[1.0, 0.5]",
                ),
            ],
        )
    )
