from __future__ import annotations

import warnings

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy, line_xy, primary_line, resolve_sample_rate
from processing.smoother import smooth_moving_average


def _to_normalized(value: float, sample_rate: float | None, cutoff_mode: str) -> float:
    if cutoff_mode == "actual" and sample_rate is not None and sample_rate > 0:
        nyquist = sample_rate / 2.0
        if nyquist > 0:
            return value / nyquist
    return value


def _filter_handler(lines, params):
    xs, ys = line_xy(primary_line(lines))
    options = dict(params or {})
    mode = str(options.get("mode", "low") or "low").strip().lower()
    cutoff_mode = str(options.get("cutoff_mode", "normalized") or "normalized").strip().lower()
    order = int(options.get("order", 3) or 3)
    sample_rate = resolve_sample_rate(list(xs), options)

    try:
        import numpy as np
        from scipy.signal import butter, filtfilt
    except ImportError:
        fallback_window = max(2, int(options.get("fallback_window", 5) or 5))
        warnings.warn("scipy 不可用，回退到移动平均滤波")
        nx, ny = smooth_moving_average(list(xs), list(ys), fallback_window)
        return line_from_xy(nx, ny)

    if mode in ("bandpass", "bandstop"):
        cutoff_low_raw = float(options.get("cutoff_low", 0.1) or 0.1)
        cutoff_high_raw = float(options.get("cutoff_high", 0.4) or 0.4)
        low = max(0.001, min(0.999, _to_normalized(cutoff_low_raw, sample_rate, cutoff_mode)))
        high = max(0.001, min(0.999, _to_normalized(cutoff_high_raw, sample_rate, cutoff_mode)))
        if low >= high:
            return line_from_xy(list(xs), list(ys))
        btype = "bandpass" if mode == "bandpass" else "bandstop"
        coeffs = butter(order, [low, high], btype=btype, analog=False)
    else:
        cutoff = float(options.get("cutoff", 0.1) or 0.1)
        cutoff = max(0.001, min(0.999, _to_normalized(cutoff, sample_rate, cutoff_mode)))
        btype = "high" if mode == "high" else "low"
        coeffs = butter(order, cutoff, btype=btype, analog=False)

    if coeffs is None or len(coeffs) < 2:
        return line_from_xy(list(xs), list(ys))
    b, a = coeffs[0], coeffs[1]
    return line_from_xy(list(xs), filtfilt(b, a, np.array(ys)).tolist())


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="filter",
            name="滤波",
            handler=_filter_handler,
            description="进行低通或高通滤波，去除不需要的频率成分。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(
                    key="mode",
                    label="滤波模式",
                    field_type="selective",
                    default="low",
                    choices=["low", "high", "bandpass", "bandstop"],
                ),
                ExtensionConfigField(
                    key="cutoff_mode",
                    label="截止频率模式",
                    field_type="selective",
                    default="normalized",
                    choices=["normalized", "actual"],
                ),
                ExtensionConfigField(key="cutoff", label="截止频率 (low/high)", field_type="number", default=0.2),
                ExtensionConfigField(key="cutoff_low", label="低频截止 (band)", field_type="number", default=0.1),
                ExtensionConfigField(key="cutoff_high", label="高频截止 (band)", field_type="number", default=0.4),
                ExtensionConfigField(key="order", label="滤波阶数", field_type="integer", default=3, min_value=1),
                ExtensionConfigField(key="sampling_rate", label="采样率", field_type="number", default=1.0),
                ExtensionConfigField(key="fallback_window", label="回退窗口（无 scipy 时）", field_type="integer", default=5, min_value=2),
            ],
        )
    )
