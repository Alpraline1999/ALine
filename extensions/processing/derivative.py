from __future__ import annotations

from core.extension_api import ProcessingExtension
from processing.extension_tools import BUILTIN_EXTENSION_VERSION, coerce_processing_handler_call, primary_series_xy


def _derivative_handler(inputs_or_xs, ys_or_params=None, params=None, lines=None):
    inputs, _options = coerce_processing_handler_call(inputs_or_xs, ys_or_params, params, lines=lines)
    x_values, y_values = primary_series_xy(inputs)
    count = len(x_values)
    if count < 2:
        return x_values, y_values
    try:
        import numpy as np

        derivative = np.gradient(np.array(y_values), np.array(x_values)).tolist()
    except ImportError:
        derivative = [0.0] * count
        for index in range(1, count - 1):
            delta_x = x_values[index + 1] - x_values[index - 1]
            derivative[index] = (y_values[index + 1] - y_values[index - 1]) / delta_x if delta_x else 0.0
        derivative[0] = (y_values[1] - y_values[0]) / (x_values[1] - x_values[0]) if x_values[1] != x_values[0] else 0.0
        derivative[-1] = (y_values[-1] - y_values[-2]) / (x_values[-1] - x_values[-2]) if x_values[-1] != x_values[-2] else 0.0
    return x_values, derivative


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="derivative",
            name="导数",
            handler=_derivative_handler,
            description="计算一阶导数，观察变化速率。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
        )
    )
