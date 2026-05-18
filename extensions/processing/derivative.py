from __future__ import annotations

import numpy as np

from core.extension_api import ExtensionConfigField, ProcessingExtension
from processing.smoother import smooth_savgol
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy, line_xy, primary_line


def _derivative_handler(lines, params):
    x_values, y_values = line_xy(primary_line(lines))
    options = dict(params or {})
    count = len(x_values)
    if count < 2:
        return line_from_xy(x_values, y_values)

    order = max(1, min(4, int(options.get("order", 1) or 1)))
    pre_smooth = int(options.get("pre_smooth", 0) or 0)

    current_y = np.array(y_values, dtype=float)

    if pre_smooth >= 3:
        try:
            _, current_y = smooth_savgol(list(x_values), current_y.tolist(), pre_smooth, 2)
            current_y = np.array(current_y, dtype=float)
        except Exception:
            pass

    for _ in range(order):
        current_y = np.gradient(current_y, np.array(x_values, dtype=float))

    return line_from_xy(x_values, current_y.tolist())


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="derivative",
            name="导数",
            handler=_derivative_handler,
            description="计算一阶或多阶导数。支持预平滑以减少噪声放大。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(key="order", label="导数阶数", field_type="integer", default=1, min_value=1, max_value=4),
                ExtensionConfigField(key="pre_smooth", label="预平滑窗口", field_type="integer", default=0, min_value=0, max_value=51,
                                     description="计算导数前先平滑数据；0=不预平滑"),
            ],
        )
    )
