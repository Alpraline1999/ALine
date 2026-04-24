from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.base_tools import VERSION, _resolve_sample_rate


def _filter_handler(xs, ys, params, lines=None):
    del lines
    options = dict(params or {})
    cutoff = float(options.get("cutoff", 0.1))
    order = int(options.get("order", 4))
    mode = options.get("mode", "low")
    cutoff_mode = str(options.get("cutoff_mode", "normalized") or "normalized").strip().lower()
    sample_rate = _resolve_sample_rate(list(xs), options)
    if cutoff_mode == "actual":
        if sample_rate is None or sample_rate <= 0:
            return list(xs), list(ys)
        nyquist = sample_rate / 2.0
        if nyquist <= 0:
            return list(xs), list(ys)
        cutoff = cutoff / nyquist
    cutoff = max(0.001, min(0.999, cutoff))
    try:
        import numpy as np
        from scipy.signal import butter, filtfilt

        btype = "high" if mode == "high" else "low"
        coeffs = butter(order, cutoff, btype=btype, analog=False)
        if coeffs is None or len(coeffs) < 2:
            return list(xs), list(ys)
        b, a = coeffs[0], coeffs[1]
        return list(xs), filtfilt(b, a, np.array(ys)).tolist()
    except ImportError:
        return list(xs), list(ys)


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="filter",
            name="滤波",
            handler=_filter_handler,
            description="进行低通或高通滤波，去除不需要的频率成分。",
            version=VERSION,
            lines_number=(1, 1),
            settings=True,
            config_fields=[
                ExtensionConfigField(
                    key="mode",
                    label="滤波模式",
                    field_type="selective",
                    default="low",
                    choices=["low", "high"],
                ),
                ExtensionConfigField(
                    key="cutoff_mode",
                    label="截止频率模式",
                    field_type="selective",
                    default="normalized",
                    choices=["normalized", "actual"],
                ),
                ExtensionConfigField(key="cutoff", label="截止频率", field_type="number", default=0.2),
                ExtensionConfigField(key="order", label="滤波阶数", field_type="integer", default=3, min_value=1),
                ExtensionConfigField(key="sampling_rate", label="采样率", field_type="number", default=1.0),
            ],
        )
    )
