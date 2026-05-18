from __future__ import annotations

import numpy as np

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, baseline_correction, line_from_xy, line_xy, primary_line


def _integral_handler(lines, params):
    x_values, y_values = line_xy(primary_line(lines))
    options = dict(params or {})
    cumulative = bool(options.get("cumulative", False))
    baseline = str(options.get("baseline", "none") or "none").strip().lower()
    count = len(x_values)
    if count < 2:
        return line_from_xy(x_values, y_values)

    xs = np.array(x_values, dtype=float)
    ys = np.array(y_values, dtype=float)
    ys = baseline_correction(xs, ys, baseline)

    try:
        from scipy.integrate import cumulative_trapezoid

        cumulative_values = cumulative_trapezoid(ys, xs, initial=0.0).tolist()
    except ImportError:
        cumulative_values = [0.0]
        for index in range(1, count):
            cumulative_values.append(
                cumulative_values[-1] + (ys[index] + ys[index - 1]) * (xs[index] - xs[index - 1]) / 2
            )

    return line_from_xy(x_values, cumulative_values if cumulative else [cumulative_values[-1]] * count)


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="integral",
            name="积分",
            handler=_integral_handler,
            description="计算积分或累积积分，支持基线校正。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(key="cumulative", label="累计积分", field_type="boolean", default=False),
                ExtensionConfigField(
                    key="baseline",
                    label="基线校正",
                    field_type="selective",
                    default="none",
                    choices=["none", "constant", "linear"],
                    description="none=无校正, constant=减去起点, linear=减去首尾连线",
                ),
            ],
        )
    )
