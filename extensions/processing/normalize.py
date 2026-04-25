from __future__ import annotations

import math

from core.extension_api import ExtensionConfigField, ProcessingExtension
from processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy, line_xy, primary_line


def _normalize_handler(lines, params):
    xs, ys = line_xy(primary_line(lines))
    options = dict(params or {})
    mode = options.get("mode", "minmax")
    if not ys:
        return line_from_xy(list(xs), list(ys))
    try:
        import numpy as np

        ay = np.asarray(ys, dtype=float)
        if mode == "minmax":
            mn, mx = ay.min(), ay.max()
            normalized = ((ay - mn) / (mx - mn or 1.0)).tolist()
        elif mode == "zscore":
            std = ay.std() or 1.0
            normalized = ((ay - ay.mean()) / std).tolist()
        else:
            normalized = list(ys)
    except ImportError:
        count = len(ys)
        if mode == "minmax":
            mn, mx = min(ys), max(ys)
            rng = mx - mn or 1.0
            normalized = [(value - mn) / rng for value in ys]
        elif mode == "zscore":
            mean = sum(ys) / count
            std = math.sqrt(sum((value - mean) ** 2 for value in ys) / count) or 1.0
            normalized = [(value - mean) / std for value in ys]
        else:
            normalized = list(ys)
    return line_from_xy(list(xs), normalized)


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="normalize",
            name="归一化",
            handler=_normalize_handler,
            description="按 min-max 或 z-score 归一化 Y 序列。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(
                    key="mode",
                    label="归一化方式",
                    field_type="selective",
                    default="minmax",
                    choices=["minmax", "zscore"],
                )
            ],
        )
    )
