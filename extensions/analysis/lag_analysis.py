from __future__ import annotations

import math

import numpy as np

from core.extension_api import AnalysisExtension, ExtensionConfigField
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, align_lines_to_common_x, line_from_xy, line_xy, normalize_lines


def _pearson(left, right) -> float:
    left_arr = np.asarray(left, dtype=float)
    right_arr = np.asarray(right, dtype=float)
    if left_arr.size < 2 or right_arr.size < 2:
        return 0.0
    left_std = float(left_arr.std())
    right_std = float(right_arr.std())
    if left_std <= 1e-12 or right_std <= 1e-12:
        return 0.0
    centered_left = left_arr - float(left_arr.mean())
    centered_right = right_arr - float(right_arr.mean())
    return float(np.mean(centered_left * centered_right) / (left_std * right_std))


def _handler(lines, params):
    normalized_lines = normalize_lines(lines)
    if len(normalized_lines) < 2:
        raise ValueError("lag_analysis 需要两条输入曲线")
    options = dict(params or {})
    aligned_lines, warnings = align_lines_to_common_x(normalized_lines[:2], options)
    if len(aligned_lines) < 2:
        raise ValueError("对齐后有效曲线不足 2 条")
    x_values, left_y = line_xy(aligned_lines[0])
    _right_x, right_y = line_xy(aligned_lines[1])
    y1 = list(float(value) for value in left_y)
    y2 = list(float(value) for value in right_y)
    max_lag = max(1, int(options.get("max_lag", 25) or 25))
    lags = []
    correlations = []
    for lag in range(-max_lag, max_lag + 1):
        if lag < 0:
            current_left = y1[-lag:]
            current_right = y2[: len(current_left)]
        elif lag > 0:
            current_left = y1[:-lag]
            current_right = y2[lag:]
        else:
            current_left = y1
            current_right = y2
        sample_count = min(len(current_left), len(current_right))
        if sample_count < 3:
            continue
        corr = _pearson(current_left[:sample_count], current_right[:sample_count])
        lags.append(lag)
        correlations.append(corr)
    if not lags:
        raise ValueError("有效相关滞后样本不足")
    sample_spacing = 1.0
    if len(x_values) >= 2:
        sample_spacing = float((float(x_values[-1]) - float(x_values[0])) / max(1, len(x_values) - 1))
    lag_x = [float(lag) * sample_spacing for lag in lags]
    best_index = max(range(len(correlations)), key=lambda index: abs(correlations[index]))
    best_lag = lags[best_index]
    best_lag_x = lag_x[best_index]
    best_corr = correlations[best_index]
    result = {
        "analysis_type": "lag_analysis",
        "best_lag_samples": int(best_lag),
        "best_lag_x": float(best_lag_x),
        "best_correlation": float(best_corr),
        "alignment_note": warnings[0] if warnings else "",
        "summary_items": [
            {"label": "最佳滞后 (采样点)", "value": int(best_lag)},
            {"label": "最佳滞后 (X)", "value": float(best_lag_x)},
            {"label": "相关系数", "value": f"{best_corr:.6f}"},
        ],
        "lines": [
            {"line_name": "滞后相关曲线", "line": line_from_xy(lag_x, correlations)},
            {"line_name": "最佳滞后", "line": line_from_xy([best_lag_x], [best_corr])},
        ],
        "_plot_series": [
            {"name": "滞后相关", "line": "滞后相关曲线", "color": "#0078D4"},
            {"name": "最佳滞后", "line": "最佳滞后", "kind": "markers", "marker": "D", "size": 56, "color": "#D13438"},
        ],
    }
    if warnings:
        result["summary_items"].append({"label": "对齐说明", "value": warnings[0]})
    return result


def register_extensions(registry) -> None:
    registry.register_analysis(
        AnalysisExtension(
            type="lag_analysis",
            name="滞后相关",
            handler=_handler,
            description="对两条曲线做对齐后滞后相关扫描，给出最佳相关滞后。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(2, 2),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(key="max_lag", label="最大滞后点数", field_type="integer", default=25, min_value=1),
                ExtensionConfigField(key="align_mode", label="对齐方式", field_type="selective", default="auto", choices=("auto", "strict")),
                ExtensionConfigField(key="resample_mode", label="重采样方式", field_type="selective", default="count", choices=("count", "spacing")),
                ExtensionConfigField(key="n", label="对齐点数", field_type="integer", default=400, min_value=2),
                ExtensionConfigField(key="step", label="对齐步长", field_type="number", default=0.1, min_value=0.0, step=0.1),
            ],
        )
    )
