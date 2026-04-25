from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from processing.extension_tools import BUILTIN_EXTENSION_VERSION, coerce_processing_handler_call, primary_series_xy


def _integral_handler(inputs_or_xs, ys_or_params=None, params=None, lines=None):
    inputs, options = coerce_processing_handler_call(inputs_or_xs, ys_or_params, params, lines=lines)
    x_values, y_values = primary_series_xy(inputs)
    cumulative = bool(options.get("cumulative", True))
    count = len(x_values)
    if count < 2:
        return x_values, y_values
    try:
        import numpy as np
        from scipy.integrate import cumulative_trapezoid

        cumulative_values = cumulative_trapezoid(np.array(y_values), np.array(x_values), initial=0.0).tolist()
        return (x_values, cumulative_values) if cumulative else (x_values, [cumulative_values[-1]] * count)
    except ImportError:
        accumulated = 0.0
        values = [0.0]
        for index in range(1, count):
            accumulated += (y_values[index] + y_values[index - 1]) * (x_values[index] - x_values[index - 1]) / 2
            values.append(accumulated)
        return (x_values, values) if cumulative else (x_values, [values[-1]] * count)


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="integral",
            name="积分",
            handler=_integral_handler,
            description="计算积分或累积积分。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(key="cumulative", label="累计积分", field_type="boolean", default=False)
            ],
        )
    )
