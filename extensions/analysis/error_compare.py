from __future__ import annotations

import math
from typing import Any, Dict, List

import numpy as np

from core.extension_api import AnalysisExtension
from extensions.processing.extension_tools import (
    BUILTIN_EXTENSION_VERSION as VERSION,
    align_lines_to_common_x,
    line_from_xy,
    line_xy,
    normalize_lines,
)


def compute_error_metrics(xs1: List[float], ys1: List[float], xs2: List[float], ys2: List[float]) -> Dict[str, Any]:
    n = min(len(xs1), len(ys1), len(xs2), len(ys2))
    if n < 2:
        raise ValueError("误差比较至少需要 2 个对齐数据点")
    xs = list(xs1[:n])
    ref = np.array(ys1[:n], dtype=float)
    cmp = np.array(ys2[:n], dtype=float)
    error_y = ref - cmp
    abs_error = np.abs(error_y)
    mae = float(np.mean(abs_error))
    rmse = float(np.sqrt(np.mean(error_y ** 2)))
    mean_error = float(np.mean(error_y))
    max_abs_error = float(np.max(abs_error))

    # MAPE
    non_zero_mask = ref != 0
    mape = float(np.mean(np.abs(error_y[non_zero_mask] / ref[non_zero_mask]))) * 100 if np.any(non_zero_mask) else None

    # SMAPE
    denom = np.abs(ref) + np.abs(cmp)
    valid = denom > 0
    smape = float(np.mean(2.0 * np.abs(error_y[valid]) / denom[valid])) * 100 if np.any(valid) else 0.0

    # R²
    ss_res = float(np.sum(error_y ** 2))
    ss_tot = float(np.sum((ref - np.mean(ref)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else None

    # Bias
    bias_ratio = mean_error / mae if mae > 0 else 0.0

    # Relative MAE
    non_zero_ref = ref[ref != 0]
    if len(non_zero_ref) > 0:
        relative_errors = np.abs(error_y[ref != 0] / non_zero_ref)
        relative_mae = float(np.mean(relative_errors))
    else:
        relative_mae = None

    return {
        "analysis_type": "error_compare",
        "n": n,
        "error_x": xs,
        "error_y": error_y.tolist(),
        "mae": mae,
        "rmse": rmse,
        "mean_error": mean_error,
        "max_abs_error": max_abs_error,
        "relative_mae": relative_mae,
        "mape": mape,
        "smape": smape,
        "r2": r2,
        "bias_ratio": bias_ratio,
    }


def _handler(lines, params):
    normalized_lines = normalize_lines(lines)
    if len(normalized_lines) < 2:
        raise ValueError("error_compare 需要两条输入数据")

    aligned_lines, _warnings = align_lines_to_common_x(normalized_lines[:2], {"align_mode": "auto"})
    if len(aligned_lines) < 2:
        raise ValueError("对齐后有效曲线不足 2 条")

    x1, y1 = line_xy(aligned_lines[0])
    x2, y2 = line_xy(aligned_lines[1])
    result = compute_error_metrics(x1, y1, x2, y2)
    error_line = line_from_xy(result.get("error_x", []), result.get("error_y", []))
    result["summary_items"] = [
        {"label": "MAE", "value": result.get("mae", 0)},
        {"label": "RMSE", "value": result.get("rmse", 0)},
        {"label": "平均误差", "value": result.get("mean_error", 0)},
        {"label": "最大绝对误差", "value": result.get("max_abs_error", 0)},
    ]
    if result.get("relative_mae") is not None:
        result["summary_items"].append({"label": "相对平均误差", "value": result.get("relative_mae")})
    if result.get("mape") is not None:
        result["summary_items"].append({"label": "MAPE", "value": f'{result["mape"]:.2f}%'})
    result["summary_items"].append({"label": "SMAPE", "value": f'{result["smape"]:.2f}%'})
    r2 = result.get("r2")
    if r2 is not None:
        result["summary_items"].append({"label": "R²", "value": f"{r2:.6f}"})
    result["summary_items"].append({"label": "偏置指标", "value": f'{result["bias_ratio"]:.4f}'})
    result["lines"] = [
        {"line_name": "误差曲线", "line": error_line},
    ]
    result["_plot_series"] = [
        {"name": "误差", "line": "误差曲线", "color": "#D13438", "line_width": 1.5},
    ]
    result["analysis_type"] = "error_compare"
    return result


def register_extensions(registry) -> None:
    registry.register_analysis(
        AnalysisExtension(
            type="error_compare",
            name="误差对比",
            handler=_handler,
            description="比较两条曲线的误差指标（MAE/RMSE/MAPE/SMAPE/R²）并输出误差曲线。",
            version=VERSION,
            lines_number=(2, 2),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            report_placeholders=[
                {"token": "{{mae}}", "label": "MAE", "description": "平均绝对误差。"},
                {"token": "{{rmse}}", "label": "RMSE", "description": "均方根误差。"},
                {"token": "{{mean_error}}", "label": "平均误差", "description": "有符号平均误差。"},
                {"token": "{{max_abs_error}}", "label": "最大绝对误差", "description": "最大绝对误差值。"},
            ],
        )
    )
