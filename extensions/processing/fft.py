from __future__ import annotations

import numpy as np

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.extension_tools import (
    BUILTIN_EXTENSION_VERSION,
    apply_window,
    line_from_xy,
    line_xy,
    primary_line,
    resolve_sample_rate,
)


def _fft_handler(lines, params):
    x_values, y_values = line_xy(primary_line(lines))
    options = dict(params or {})
    count = len(y_values)
    if count < 2:
        return line_from_xy(x_values, y_values)

    output = options.get("output", "amplitude")
    detrend = bool(options.get("detrend", True))
    window_name = str(options.get("window", "hann") or "hann").strip().lower()
    sample_rate = resolve_sample_rate(x_values, options)

    y_arr = np.asarray(y_values, dtype=float)
    if detrend:
        y_arr = y_arr - y_arr.mean()
    window = apply_window(count, window_name)
    windowed = y_arr * window
    step = 1.0 / sample_rate if sample_rate and sample_rate > 0 else 1.0
    freq = np.fft.rfftfreq(count, d=step)
    spectrum = np.fft.rfft(windowed)
    if output == "power":
        values = (np.abs(spectrum) ** 2 / max(1, count)).tolist()
    elif output == "phase":
        values = np.angle(spectrum).tolist()
    else:
        values = (np.abs(spectrum) / max(1, count)).tolist()
    return line_from_xy(freq.tolist(), values)


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="fft",
            name="FFT",
            handler=_fft_handler,
            description="将时域或空间域信号转换为频域频谱，支持多种窗函数和输出类型。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(
                    key="output",
                    label="输出类型",
                    field_type="selective",
                    default="amplitude",
                    choices=["amplitude", "power", "phase"],
                ),
                ExtensionConfigField(
                    key="window",
                    label="窗函数",
                    field_type="selective",
                    default="hann",
                    choices=["hann", "hamming", "blackman", "rect"],
                ),
                ExtensionConfigField(key="detrend", label="去直流分量", field_type="boolean", default=True),
                ExtensionConfigField(key="sampling_rate", label="采样率", field_type="number", default=1.0),
            ],
        )
    )
