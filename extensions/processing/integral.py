from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy, line_xy, primary_line


def _integral_handler(lines, params):
    x_values, y_values = line_xy(primary_line(lines))
    options = dict(params or {})
    cumulative = bool(options.get("cumulative", False))
    count = len(x_values)
    if count < 2:
        return line_from_xy(x_values, y_values)
    try:
        import numpy as np
        from scipy.integrate import cumulative_trapezoid

        cumulative_values = cumulative_trapezoid(np.array(y_values), np.array(x_values), initial=0.0).tolist()
        return line_from_xy(x_values, cumulative_values if cumulative else [cumulative_values[-1]] * count)
    except ImportError:
        accumulated = 0.0
        values = [0.0]
        for index in range(1, count):
            accumulated += (y_values[index] + y_values[index - 1]) * (x_values[index] - x_values[index - 1]) / 2
            values.append(accumulated)
        return line_from_xy(x_values, values if cumulative else [values[-1]] * count)


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
