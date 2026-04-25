from __future__ import annotations

import math

from core.extension_api import ExtensionConfigField, ProcessingExtension
from processing.extension_tools import BUILTIN_EXTENSION_VERSION, coerce_processing_handler_call, primary_series_xy


def _crop_xy(xs, ys, params):
    options = dict(params or {})
    raw_x_min = options.get("x_min")
    raw_x_max = options.get("x_max")
    x_min = -math.inf if raw_x_min in (None, "") else float(raw_x_min)
    x_max = math.inf if raw_x_max in (None, "") else float(raw_x_max)
    try:
        import numpy as np

        ax = np.asarray(xs, dtype=float)
        ay = np.asarray(ys, dtype=float)
        mask = (ax >= x_min) & (ax <= x_max)
        return ax[mask].tolist(), ay[mask].tolist()
    except ImportError:
        pairs = [(x, y) for x, y in zip(xs, ys) if x_min <= x <= x_max]
        if not pairs:
            return [], []
        nx, ny = zip(*pairs)
        return list(nx), list(ny)


def crop_handler(inputs_or_xs, ys_or_params=None, params=None, lines=None):
    inputs, options = coerce_processing_handler_call(inputs_or_xs, ys_or_params, params, lines=lines)
    xs, ys = primary_series_xy(inputs)
    return _crop_xy(xs, ys, options)


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="crop",
            name="裁剪",
            handler=crop_handler,
            description="按 X 轴范围裁剪数据，只保留目标区间。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(key="x_min", label="X 最小值", field_type="number", default=None),
                ExtensionConfigField(key="x_max", label="X 最大值", field_type="number", default=None),
            ],
        )
    )
