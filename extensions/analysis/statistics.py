from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from core.extension_api import AnalysisExtension
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION as VERSION, line_xy, primary_line


def compute_statistics(xs: List[float], ys: List[float]) -> Dict[str, Any]:
    def _stats(vals: List[float], label: str) -> dict:
        n = len(vals)
        if n == 0:
            return {}
        a = np.asarray(vals, dtype=float)
        mean = float(a.mean())
        std = float(a.std())
        centered = a - mean
        skew = float(np.mean(centered ** 3) / (std ** 3)) if std > 1e-12 else 0.0
        kurt = float(np.mean(centered ** 4) / (std ** 4)) - 3.0 if std > 1e-12 else 0.0
        p25 = float(np.percentile(a, 25))
        p75 = float(np.percentile(a, 75))
        iqr = p75 - p25
        ci_95 = 1.96 * std / np.sqrt(n) if n > 1 else 0.0
        result = {
            f"{label}_n": n,
            f"{label}_min": float(a.min()),
            f"{label}_max": float(a.max()),
            f"{label}_mean": mean,
            f"{label}_std": std,
            f"{label}_median": float(np.median(a)),
            f"{label}_p25": p25,
            f"{label}_p75": p75,
            f"{label}_iqr": iqr,
            f"{label}_cv": std / mean if mean != 0 else float("nan"),
            f"{label}_ci_95": ci_95,
            f"{label}_skewness": skew,
            f"{label}_kurtosis": kurt,
        }
        if n >= 3:
            try:
                from scipy.stats import jarque_bera
                jb_stat, jb_p = jarque_bera(a)
                result[f"{label}_jb_stat"] = float(jb_stat)
                result[f"{label}_jb_p"] = float(jb_p)
            except ImportError:
                pass
            if n <= 5000:
                try:
                    from scipy.stats import shapiro
                    sh_stat, sh_p = shapiro(a)
                    result[f"{label}_shapiro_stat"] = float(sh_stat)
                    result[f"{label}_shapiro_p"] = float(sh_p)
                except ImportError:
                    pass
        return result

    result = {"n": min(len(xs), len(ys))}
    result.update(_stats(xs, "x"))
    result.update(_stats(ys, "y"))
    return result


def _handler(lines, params):
    if not lines:
        raise ValueError("statistics 需要至少一条输入数据")
    xs, ys = line_xy(primary_line(lines))
    result = compute_statistics(xs, ys)
    y_mean = result.get("y_mean")
    y_ci = result.get("y_ci_95")
    y_cv = result.get("y_cv")
    summary = [
        {"label": "X 最小值", "value": result.get("x_min", "")},
        {"label": "X 最大值", "value": result.get("x_max", "")},
        {"label": "Y 最小值", "value": result.get("y_min", "")},
        {"label": "Y 最大值", "value": result.get("y_max", "")},
        {"label": "Y 均值", "value": y_mean},
        {"label": "Y 标准差", "value": result.get("y_std", "")},
    ]
    if y_cv is not None and not (isinstance(y_cv, float) and np.isnan(y_cv)):
        summary.append({"label": "Y 变异系数 (CV)", "value": f"{y_cv:.4f}"})
    if y_ci is not None:
        summary.append({"label": "Y 均值 95%CI", "value": f"({y_mean - y_ci:.4f}, {y_mean + y_ci:.4f})"})
    y_skew = result.get("y_skewness")
    y_kurt = result.get("y_kurtosis")
    if y_skew is not None:
        summary.append({"label": "Y 偏度", "value": f"{y_skew:.4f}"})
    if y_kurt is not None:
        summary.append({"label": "Y 峰度", "value": f"{y_kurt:.4f}"})
    y_jb_p = result.get("y_jb_p")
    if y_jb_p is not None:
        normality = "正态" if y_jb_p > 0.05 else "非正态"
        summary.append({"label": "正态性 (JB)", "value": f"p={y_jb_p:.4g} ({normality})"})
    result["summary_items"] = summary
    result["analysis_type"] = "statistics"
    return result


def register_extensions(registry) -> None:
    registry.register_analysis(
        AnalysisExtension(
            type="statistics",
            name="统计分析",
            handler=_handler,
            description="计算当前曲线的常用统计量，包括 IQR、CV、置信区间与正态性检验。",
            version=VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            report_placeholders=[
                {"token": "{{n}}", "label": "样本数", "description": "曲线采样点总数。"},
                {"token": "{{x_min}}", "label": "X 最小值", "description": "X 轴最小值。"},
                {"token": "{{x_max}}", "label": "X 最大值", "description": "X 轴最大值。"},
                {"token": "{{y_min}}", "label": "Y 最小值", "description": "Y 轴最小值。"},
                {"token": "{{y_max}}", "label": "Y 最大值", "description": "Y 轴最大值。"},
                {"token": "{{y_mean}}", "label": "Y 均值", "description": "Y 轴均值。"},
                {"token": "{{y_std}}", "label": "Y 标准差", "description": "Y 轴标准差。"},
            ],
        )
    )
