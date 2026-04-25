from __future__ import annotations

import cmath
import math

from core.extension_api import ExtensionConfigField, ProcessingExtension
from processing.extension_tools import BUILTIN_EXTENSION_VERSION, coerce_processing_handler_call, primary_series_xy, resolve_sample_rate


def _fft_handler(inputs_or_xs, ys_or_params=None, params=None, lines=None):
    inputs, options = coerce_processing_handler_call(inputs_or_xs, ys_or_params, params, lines=lines)
    x_values, y_values = primary_series_xy(inputs)
    count = len(y_values)
    if count < 2:
        return x_values, y_values

    output = options.get("output", "amplitude")
    detrend = bool(options.get("detrend", True))
    sample_rate = resolve_sample_rate(x_values, options)
    try:
        import numpy as np

        y_arr = np.asarray(y_values, dtype=float)
        if detrend:
            y_arr = y_arr - y_arr.mean()
        step = 1.0 / sample_rate if sample_rate and sample_rate > 0 else 1.0
        freq = np.fft.rfftfreq(count, d=step)
        spectrum = np.fft.rfft(y_arr)
        if output == "power":
            values = (np.abs(spectrum) ** 2 / max(1, count)).tolist()
        else:
            values = (np.abs(spectrum) / max(1, count)).tolist()
        return freq.tolist(), values
    except ImportError:
        step = 1.0 / sample_rate if sample_rate and sample_rate > 0 else 1.0
        signal = list(y_values)
        if detrend:
            mean = sum(signal) / len(signal)
            signal = [value - mean for value in signal]
        half = count // 2
        freq: list[float] = []
        values: list[float] = []
        for k in range(half + 1):
            total = 0j
            for index, sample in enumerate(signal):
                total += sample * cmath.exp(-2j * math.pi * k * index / count)
            amp = abs(total) / max(1, count)
            freq.append(k / (count * step))
            values.append(amp * amp if output == "power" else amp)
        return freq, values


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="fft",
            name="FFT",
            handler=_fft_handler,
            description="将时域或空间域信号转换为频域频谱。",
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
                    choices=["amplitude", "power"],
                ),
                ExtensionConfigField(key="detrend", label="去直流分量", field_type="boolean", default=True),
                ExtensionConfigField(key="sampling_rate", label="采样率", field_type="number", default=1.0),
            ],
        )
    )
