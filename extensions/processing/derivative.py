from __future__ import annotations

from core.extension_api import ProcessingExtension
from extensions.processing.base_tools import VERSION


def _derivative_handler(xs, ys, params, lines=None):
    del params, lines
    x_values = list(xs)
    y_values = list(ys)
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
            version=VERSION,
            lines_number=(1, 1),
            settings=True,
                source_kind="builtin",
        )
    )
