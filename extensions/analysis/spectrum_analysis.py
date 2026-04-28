from __future__ import annotations

import numpy as np

from core.extension_api import AnalysisExtension, ExtensionConfigField
from extensions.processing.extension_tools import line_from_xy, line_xy, primary_line


def _as_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _resolve_sampling_rate(xs, params):
    configured = _as_float(params.get("sampling_rate", 0.0), 0.0)
    if configured > 0:
        return configured
    if len(xs) >= 2:
        diffs = np.diff(xs)
        positive = diffs[np.isfinite(diffs) & (diffs > 0)]
        if positive.size:
            return float(1.0 / np.mean(positive))
    return 1.0


def _window_values(window_name, size):
    name = str(window_name or "hann").strip().lower()
    if name == "hamming":
        return np.hamming(size)
    if name == "blackman":
        return np.blackman(size)
    if name in {"rect", "rectangle", "boxcar"}:
        return np.ones(size)
    return np.hanning(size)


def spectrum_analysis(lines, params):
    xs_raw, ys_raw = line_xy(primary_line(lines))
    xs = np.asarray(list(xs_raw), dtype=float)
    ys = np.asarray(list(ys_raw), dtype=float)
    if ys.size < 2:
        raise ValueError("频谱分析至少需要 2 个采样点")

    sampling_rate = _resolve_sampling_rate(xs, params)
    detrend = bool(params.get("detrend", True))
    centered = ys - float(np.mean(ys)) if detrend else ys
    window_name = str(params.get("window", "hann") or "hann").strip().lower()
    window = _window_values(window_name, centered.size)
    spectrum = np.fft.rfft(centered * window)
    freqs = np.fft.rfftfreq(centered.size, d=1.0 / sampling_rate)
    amplitudes = np.abs(spectrum) * (2.0 / max(centered.size, 1))
    if amplitudes.size:
        amplitudes[0] = amplitudes[0] / 2.0

    max_frequency = _as_float(params.get("max_frequency", 0.0), 0.0)
    if max_frequency > 0:
        mask = freqs <= max_frequency
        freqs = freqs[mask]
        amplitudes = amplitudes[mask]

    dominant_index = int(np.argmax(amplitudes[1:]) + 1) if amplitudes.size > 1 else 0
    dominant_frequency = float(freqs[dominant_index]) if freqs.size else 0.0
    dominant_amplitude = float(amplitudes[dominant_index]) if amplitudes.size else 0.0
    line_color = str(params.get("line_color", "#0078D4"))
    spectrum_line = line_from_xy(freqs.tolist(), amplitudes.tolist())

    return {
        "analysis_type": "spectrum_analysis",
        "sampling_rate": float(sampling_rate),
        "window": window_name,
        "frequency_resolution": float(sampling_rate / centered.size),
        "dominant_frequency": dominant_frequency,
        "dominant_amplitude": dominant_amplitude,
        "spectrum_points": int(freqs.size),
        "x_label": "频率 (Hz)",
        "y_label": "幅值",
        "plot_title": "当前数据 频谱",
        "lines": [
            {
                "line_name": "频谱",
                "line": spectrum_line,
            }
        ],
        "_plot_series": [
            {
                "name": "频谱",
                "line": "频谱",
                "color": line_color,
            }
        ],
    }


def register_extensions(registry):
    registry.register_analysis(
        AnalysisExtension(
            type="spectrum_analysis",
            name="频谱分析",
            handler=spectrum_analysis,
            description="基于 FFT 计算主曲线的频谱分布，并返回主频与频率分辨率。",
            version="0.1.0",
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="experimental",
            config_fields=[
                ExtensionConfigField(
                    key="sampling_rate",
                    description="采样率，<= 0 时会尝试根据 X 间距自动推断。",
                    field_type="number",
                    default=0.0,
                ),
                ExtensionConfigField(
                    key="window",
                    description="频谱分析前使用的窗函数。",
                    field_type="selective",
                    default="hann",
                    choices=("hann", "hamming", "blackman", "rect"),
                ),
                ExtensionConfigField(
                    key="detrend",
                    description="分析前是否先减去均值。",
                    field_type="boolean",
                    default=True,
                ),
                ExtensionConfigField(
                    key="max_frequency",
                    description="只保留不高于该值的频谱，<= 0 表示保留全频段。",
                    field_type="number",
                    default=0.0,
                ),
                ExtensionConfigField(
                    key="line_color",
                    description="频谱曲线颜色。",
                    field_type="color",
                    default="#0078D4",
                ),
            ],
            report_placeholders=[
                {"token": "{{dominant_frequency}}", "label": "主频", "description": "频谱主峰对应的频率。"},
                {"token": "{{dominant_amplitude}}", "label": "主峰幅值", "description": "频谱主峰对应的幅值。"},
                {"token": "{{sampling_rate}}", "label": "采样率", "description": "本次频谱分析使用的采样率。"},
                {"token": "{{frequency_resolution}}", "label": "频率分辨率", "description": "频谱频率轴分辨率。"},
                {"token": "{{spectrum_points}}", "label": "频谱点数", "description": "当前频谱输出点数。"},
            ],
        )
    )