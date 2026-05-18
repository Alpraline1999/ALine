from __future__ import annotations

import numpy as np

from core.extension_api import AnalysisExtension, ExtensionConfigField
from core.value_parsing import coerce_float
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, apply_window, line_from_xy, line_xy, primary_line


def _resolve_sampling_rate(xs, params):
    configured = coerce_float(params.get("sampling_rate", 0.0), 0.0) or 0.0
    if configured > 0:
        return configured
    if len(xs) >= 2:
        diffs = np.diff(xs)
        positive = diffs[np.isfinite(diffs) & (diffs > 0)]
        if positive.size:
            return float(1.0 / np.mean(positive))
    return 1.0


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
    window = apply_window(centered.size, window_name)
    spectrum = np.fft.rfft(centered * window)
    freqs = np.fft.rfftfreq(centered.size, d=1.0 / sampling_rate)
    amplitudes = np.abs(spectrum) * (2.0 / max(centered.size, 1))
    if amplitudes.size:
        amplitudes[0] = amplitudes[0] / 2.0

    max_frequency = coerce_float(params.get("max_frequency", 0.0), 0.0) or 0.0
    if max_frequency > 0:
        mask = freqs <= max_frequency
        freqs = freqs[mask]
        amplitudes = amplitudes[mask]

    dominant_index = int(np.argmax(amplitudes[1:]) + 1) if amplitudes.size > 1 else 0
    dominant_frequency = float(freqs[dominant_index]) if freqs.size else 0.0
    dominant_amplitude = float(amplitudes[dominant_index]) if amplitudes.size else 0.0
    line_color = str(params.get("line_color", "#0078D4"))
    log_scale = bool(params.get("log_scale", False))
    y_to_plot = amplitudes.tolist()
    if log_scale and amplitudes.size:
        min_amp = amplitudes[amplitudes > 0].min() if np.any(amplitudes > 0) else 1e-10
        amplitudes_log = np.maximum(amplitudes, min_amp)
        y_to_plot = np.log10(amplitudes_log).tolist()
    else:
        y_to_plot = amplitudes.tolist()
    spectrum_line = line_from_xy(freqs.tolist(), y_to_plot)

    return {
        "analysis_type": "spectrum_analysis",
        "sampling_rate": float(sampling_rate),
        "window": window_name,
        "frequency_resolution": float(sampling_rate / centered.size),
        "dominant_frequency": dominant_frequency,
        "dominant_amplitude": dominant_amplitude,
        "spectrum_points": int(freqs.size),
        "x_label": "频率 (Hz)",
        "y_label": "幅值 (log₁₀)" if log_scale else "幅值",
        "plot_title": "当前数据 频谱",
        "summary_items": [
            {"label": "主频", "value": f"{dominant_frequency:.6g} Hz"},
            {"label": "主峰幅值", "value": f"{dominant_amplitude:.6g}"},
            {"label": "频率分辨率", "value": f"{float(sampling_rate / centered.size):.6g} Hz"},
            {"label": "窗函数", "value": window_name},
        ],
        "lines": [
            {
                "line_name": "频谱",
                "line": spectrum_line,
            },
            {
                "line_name": "主频标记",
                "line": line_from_xy([dominant_frequency], [y_to_plot[dominant_index]]),
            },
        ],
        "_plot_series": [
            {
                "name": "频谱",
                "line": "频谱",
                "color": line_color,
            },
            {
                "name": f"主频: {dominant_frequency:.4g} Hz",
                "line": "主频标记",
                "kind": "markers",
                "marker": "D",
                "size": 60,
                "color": "#D13438",
            },
        ],
    }


def register_extensions(registry):
    registry.register_analysis(
        AnalysisExtension(
            type="spectrum_analysis",
            name="频谱分析",
            handler=spectrum_analysis,
            description="基于 FFT 计算主曲线的频谱分布，并返回主频与频率分辨率。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
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
                    key="log_scale",
                    description="纵轴使用对数坐标显示幅值。",
                    field_type="boolean",
                    default=False,
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
