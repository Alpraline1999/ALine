from __future__ import annotations

import numpy as np

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy, line_xy, primary_line


def _ifft_handler(lines, params):
    x_values, y_values = line_xy(primary_line(lines))
    options = dict(params or {})
    count = len(x_values)
    if count < 2:
        return line_from_xy(x_values, y_values)

    sample_rate = float(options.get("sampling_rate", 0.0) or 0.0)
    if sample_rate <= 0:
        diffs = np.diff(np.array(x_values, dtype=float))
        positive = diffs[np.isfinite(diffs) & (diffs > 0)]
        if positive.size > 0:
            sample_rate = float(1.0 / np.mean(positive))
        else:
            sample_rate = 1.0

    magnitude = np.asarray(y_values, dtype=float)
    n = len(magnitude)

    half_n = n
    full_n = 2 * (half_n - 1)
    symmetric = np.zeros(full_n)
    symmetric[:half_n] = magnitude
    symmetric[-half_n + 2:] = magnitude[-1:0:-1]

    time_domain = np.fft.ifft(symmetric).real
    time_values = np.arange(len(time_domain)) / sample_rate

    return line_from_xy(time_values.tolist(), time_domain.tolist())


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="ifft",
            name="逆 FFT",
            handler=_ifft_handler,
            description="将频谱从频域转换回时域（零相位重建），适合预览滤波效果与频谱包络。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="experimental",
            hidden=True,
            config_fields=[
                ExtensionConfigField(
                    key="sampling_rate",
                    label="采样率",
                    field_type="number",
                    default=0.0,
                    description="<= 0 时根据 X 间距自动推断。",
                ),
            ],
        )
    )
